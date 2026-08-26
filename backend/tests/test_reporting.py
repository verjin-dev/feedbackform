"""Reporting arithmetic, and who is allowed to see it.

The legacy get_report divided each rating tally by an unchecked count and
omitted questions nobody had answered. Both behaviours are pinned here.
"""

import pytest

from app.core.security import hash_password
from app.models import (
    Account,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Role,
)
from app.services.reporting import build_faculty_report, build_response_rate_report

PASSWORD = "reporting-password"


def _record(session, fixtures, ratings: list[int], student: Account | None = None):
    """One anonymous response plus its participation record."""
    session.add(
        EvaluationSubmission(
            term_id=fixtures["term"].id,
            student_id=(student or fixtures["student"]).id,
            assignment_id=fixtures["assignment"].id,
        )
    )
    response = EvaluationResponse(
        term_id=fixtures["term"].id, assignment_id=fixtures["assignment"].id
    )
    session.add(response)
    session.flush()
    for question, rating in zip(fixtures["questions"], ratings, strict=True):
        session.add(
            EvaluationRating(
                response_id=response.id, question_id=question.id, rating=rating
            )
        )
    session.commit()


def _record_many(session, fixtures, rows: list[list[int]]):
    """Record one response per row, each from a different student, so the
    sample clears MIN_RESPONSES_FOR_MEAN."""
    for index, ratings in enumerate(rows):
        student = (
            fixtures["student"] if index == 0 else _extra_student(session, fixtures, index)
        )
        _record(session, fixtures, ratings, student=student)


def _extra_student(session, fixtures, n: int) -> Account:
    account = Account(
        role=Role.student,
        first_name=f"Student{n}",
        last_name="Extra",
        email=f"student{n}@example.edu",
        password_hash="placeholder",
        class_group_id=fixtures["class_group"].id,
    )
    session.add(account)
    session.commit()
    return account


class TestEmptyReports:
    def test_no_responses_yields_none_not_zero(self, session, fixtures):
        """A question nobody rated is not a question rated zero."""
        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])

        [assignment] = report["assignments"]
        assert assignment["responses"] == 0
        assert assignment["mean"] is None
        for criterion in assignment["criteria"]:
            assert criterion["mean"] is None
            for question in criterion["questions"]:
                assert question["mean"] is None
                assert question["responses"] == 0

    def test_unanswered_questions_still_appear(self, session, fixtures):
        """The legacy report dropped them, so a sparse criterion read as a
        complete one."""
        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])

        [assignment] = report["assignments"]
        listed = [q["question_id"] for c in assignment["criteria"] for q in c["questions"]]
        assert listed == [q.id for q in fixtures["questions"]]

    def test_counts_are_explicit_zeros_across_all_five_ratings(self, session, fixtures):
        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])

        question = report["assignments"][0]["criteria"][0]["questions"][0]
        assert question["counts"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        assert question["percentages"] == {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0}

    def test_no_eligible_students_gives_a_none_rate_not_a_crash(
        self, session, fixtures
    ):
        """This is the division get_report performed unguarded."""
        fixtures["student"].is_active = False
        session.commit()

        report = build_response_rate_report(session, fixtures["term"])
        assert report["rows"][0]["eligible_students"] == 0
        assert report["rows"][0]["response_rate"] is None
        assert report["response_rate"] is None


class TestArithmetic:
    def test_a_unanimous_sample_reports_that_value(self, session, fixtures):
        _record_many(session, fixtures, [[5, 3]] * 5)

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        questions = report["assignments"][0]["criteria"][0]["questions"]

        assert questions[0]["mean"] == 5.0
        assert questions[1]["mean"] == 3.0
        assert questions[0]["counts"]["5"] == 5

    def test_means_average_across_responses(self, session, fixtures):
        _record_many(
            session, fixtures, [[5, 5], [5, 5], [3, 1], [3, 1], [4, 3]]
        )

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        questions = report["assignments"][0]["criteria"][0]["questions"]

        assert questions[0]["mean"] == 4.0  # (5+5+3+3+4) / 5
        assert questions[1]["mean"] == 3.0  # (5+5+1+1+3) / 5

    def test_percentages_are_of_that_questions_responses(self, session, fixtures):
        _record(session, fixtures, [5, 5])
        _record(session, fixtures, [5, 1], student=_extra_student(session, fixtures, 1))
        _record(session, fixtures, [1, 1], student=_extra_student(session, fixtures, 2))

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        first = report["assignments"][0]["criteria"][0]["questions"][0]

        assert first["counts"] == {"1": 1, "2": 0, "3": 0, "4": 0, "5": 2}
        assert first["percentages"]["5"] == pytest.approx(66.67, abs=0.01)
        assert first["percentages"]["1"] == pytest.approx(33.33, abs=0.01)
        assert sum(first["percentages"].values()) == pytest.approx(100.0, abs=0.01)

    def test_the_criterion_mean_averages_its_questions(self, session, fixtures):
        _record_many(session, fixtures, [[5, 3]] * 5)

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        assert report["assignments"][0]["criteria"][0]["mean"] == 4.0

    def test_response_rate_uses_the_class_roll_as_denominator(self, session, fixtures):
        for n in range(1, 4):
            _extra_student(session, fixtures, n)
        _record(session, fixtures, [5, 5])

        report = build_response_rate_report(session, fixtures["term"])
        row = report["rows"][0]

        assert row["eligible_students"] == 4  # the fixture student plus three
        assert row["responses"] == 1
        assert row["response_rate"] == 0.25

    def test_inactive_students_are_not_counted_as_eligible(self, session, fixtures):
        extra = _extra_student(session, fixtures, 1)
        extra.is_active = False
        session.commit()

        report = build_response_rate_report(session, fixtures["term"])
        assert report["rows"][0]["eligible_students"] == 1


class TestReportAccess:
    @pytest.fixture
    def faculty_client(self, client, session, fixtures):
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})
        return client

    def test_faculty_can_read_their_own_report(self, faculty_client, fixtures):
        response = faculty_client.get(f"/reports/faculty/{fixtures['faculty'].id}")

        assert response.status_code == 200
        assert response.json()["faculty_id"] == fixtures["faculty"].id

    def test_reports_me_returns_the_callers_own_results(self, faculty_client, fixtures):
        response = faculty_client.get("/reports/me")

        assert response.status_code == 200
        assert response.json()["faculty_id"] == fixtures["faculty"].id

    def test_faculty_cannot_read_another_instructors_report(
        self, faculty_client, session, fixtures
    ):
        """In the legacy app this was an unguarded AJAX action taking
        faculty_id from the request."""
        other = Account(
            role=Role.faculty,
            first_name="Other",
            last_name="Instructor",
            email="other.instructor@example.edu",
            password_hash="placeholder",
        )
        session.add(other)
        session.commit()

        response = faculty_client.get(f"/reports/faculty/{other.id}")
        assert response.status_code == 403

    def test_an_admin_can_read_any_report(self, admin_client, fixtures):
        response = admin_client.get(f"/reports/faculty/{fixtures['faculty'].id}")
        assert response.status_code == 200

    def test_a_student_cannot_read_reports(self, student_client, fixtures):
        assert (
            student_client.get(f"/reports/faculty/{fixtures['faculty'].id}").status_code
            == 403
        )

    def test_an_anonymous_caller_cannot_read_reports(self, client, fixtures):
        assert (
            client.get(f"/reports/faculty/{fixtures['faculty'].id}").status_code == 401
        )

    def test_response_rates_are_admin_only(self, faculty_client, student_client):
        assert faculty_client.get("/reports/response-rates").status_code == 403

    def test_an_admin_sees_response_rates(self, admin_client, fixtures):
        response = admin_client.get("/reports/response-rates")

        assert response.status_code == 200
        assert response.json()["rows"][0]["faculty_name"] == "Asha Raman"

    def test_asking_for_a_non_faculty_account_is_404(self, admin_client, fixtures):
        response = admin_client.get(f"/reports/faculty/{fixtures['student'].id}")
        assert response.status_code == 404


class TestAnonymityInReports:
    def test_no_student_identity_appears_anywhere_in_a_report(
        self, admin_client, session, fixtures
    ):
        """The report is the one place results are exposed, so it is the one
        place a leak would surface."""
        _record(session, fixtures, [5, 4])

        body = admin_client.get(f"/reports/faculty/{fixtures['faculty'].id}").text

        student = fixtures["student"]
        assert student.email not in body
        assert student.first_name not in body
        assert str(student.school_id) not in body
        assert "student_id" not in body
        assert "response_id" not in body


class TestSmallSampleHonesty:
    """Seven self-selected opinions and twenty-eight are not the same evidence,
    and the report must not present them identically."""

    def test_four_responses_publish_no_mean(self, session, fixtures):
        _record_many(session, fixtures, [[5, 5], [5, 5], [4, 4], [4, 4]])

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        assignment = report["assignments"][0]
        question = assignment["criteria"][0]["questions"][0]

        assert question["responses"] == 4
        assert question["mean"] is None
        assert question["reliability"] == "insufficient"
        assert assignment["mean"] is None

    def test_the_distribution_is_still_returned_below_the_threshold(
        self, session, fixtures
    ):
        """Withholding the mean is not the same as withholding the data. A
        reader can still see the shape of four answers."""
        _record_many(session, fixtures, [[5, 5], [5, 5], [1, 1], [1, 1]])

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        question = report["assignments"][0]["criteria"][0]["questions"][0]

        assert question["counts"] == {"1": 2, "2": 0, "3": 0, "4": 0, "5": 2}
        assert question["mean"] is None

    def test_five_responses_publish_a_mean(self, session, fixtures):
        _record_many(session, fixtures, [[4, 4]] * 5)

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        question = report["assignments"][0]["criteria"][0]["questions"][0]

        assert question["responses"] == 5
        assert question["mean"] == 4.0
        assert question["reliability"] != "insufficient"

    def test_a_published_mean_carries_an_interval(self, session, fixtures):
        _record_many(session, fixtures, [[5, 5], [4, 4], [3, 3], [5, 5], [2, 2]])

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        question = report["assignments"][0]["criteria"][0]["questions"][0]

        low, high = question["mean_range"]
        assert low < question["mean"] < high
        # A spread of 2-5 over five people is not a precise estimate, and the
        # interval should say so rather than the mean implying otherwise.
        assert high - low > 1.0

    def test_a_unanimous_sample_has_a_zero_width_interval(self, session, fixtures):
        _record_many(session, fixtures, [[4, 4]] * 6)

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        question = report["assignments"][0]["criteria"][0]["questions"][0]

        assert question["mean_range"] == (4.0, 4.0)

    def test_the_interval_never_leaves_the_scale(self, session, fixtures):
        """A mean of 5.0 must not report an upper bound of 5.4."""
        _record_many(session, fixtures, [[5, 5]] * 5 + [[4, 4]])

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        question = report["assignments"][0]["criteria"][0]["questions"][0]

        low, high = question["mean_range"]
        assert 1.0 <= low <= high <= 5.0

    def test_a_healthy_sample_is_adequate(self, session, fixtures):
        # Six responses from a class of six.
        _record_many(session, fixtures, [[4, 4]] * 6)

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        assert report["assignments"][0]["reliability"] == "adequate"

    def test_enough_responses_but_a_thin_share_of_the_class_is_flagged_low(
        self, session, fixtures
    ):
        """The thesis case: a real mean, from a small minority of the class."""
        # Offset the ids: _record_many creates students 1..5 of its own.
        for n in range(100, 129):
            _extra_student(session, fixtures, n)
        _record_many(session, fixtures, [[4, 4]] * 6)

        report = build_faculty_report(session, fixtures["faculty"], fixtures["term"])
        assignment = report["assignments"][0]

        assert assignment["responses"] == 6
        # 29 offset students, the fixture student, and the five _record_many made.
        assert assignment["eligible_students"] == 35
        assert assignment["mean"] == 4.0
        # A real mean, from 17% of the class.
        assert assignment["response_rate"] < 0.3
        assert assignment["reliability"] == "low"

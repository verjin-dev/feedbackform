"""Results over successive terms.

Feedback that cannot be compared to last time is a verdict; feedback that can
is a direction. The rules that matter here are about not drawing a line that
says something the data does not.
"""

import pytest

from app.core.security import hash_password
from app.models import (
    AcademicTerm,
    Account,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Question,
    Role,
    TeachingAssignment,
    TermStatus,
)

PASSWORD = "trend-password-here"


def make_term(session, year: str, semester: int, fixtures) -> AcademicTerm:
    """A past term with the same criterion and questions, and the same
    assignment for the same instructor."""
    term = AcademicTerm(year=year, semester=semester, status=TermStatus.closed)
    session.add(term)
    session.flush()

    for text in ("Explains concepts clearly.", "Answers questions thoroughly."):
        session.add(
            Question(
                term_id=term.id,
                criterion_id=fixtures["criterion"].id,
                text=text,
                position=1,
            )
        )
    session.add(
        TeachingAssignment(
            term_id=term.id,
            faculty_id=fixtures["faculty"].id,
            class_group_id=fixtures["class_group"].id,
            subject_id=fixtures["subject"].id,
        )
    )
    session.commit()
    return term


def student(session, fixtures, n) -> Account:
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


def fill(session, term, fixtures, rating: int, count: int, offset: int = 0):
    """`count` responses for the assignment in `term`, all at `rating`."""
    assignment = (
        session.query(TeachingAssignment).filter_by(term_id=term.id).one()
    )
    questions = session.query(Question).filter_by(term_id=term.id).all()

    for n in range(count):
        learner = student(session, fixtures, offset + n)
        session.add(
            EvaluationSubmission(
                term_id=term.id, student_id=learner.id, assignment_id=assignment.id
            )
        )
        response = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
        session.add(response)
        session.flush()
        for question in questions:
            session.add(
                EvaluationRating(
                    response_id=response.id, question_id=question.id, rating=rating
                )
            )
    session.commit()


@pytest.fixture
def faculty_client(client, session, fixtures):
    faculty = fixtures["faculty"]
    faculty.password_hash = hash_password(PASSWORD)
    session.commit()
    client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})
    return client


@pytest.fixture
def three_terms(session, fixtures):
    """2023 at 3.0, 2024 at 4.0, and the fixture's 2025-2026 at 5.0."""
    old = make_term(session, "2023-2024", 1, fixtures)
    mid = make_term(session, "2024-2025", 1, fixtures)
    fill(session, old, fixtures, 3, 6, offset=0)
    fill(session, mid, fixtures, 4, 6, offset=100)
    fill(session, fixtures["term"], fixtures, 5, 6, offset=200)
    return {"old": old, "mid": mid, "current": fixtures["term"], **fixtures}


class TestSeries:
    def test_terms_come_back_oldest_first(self, faculty_client, three_terms):
        body = faculty_client.get("/reports/me/trend").json()

        assert [t["year"] for t in body["terms"]] == [
            "2023-2024",
            "2024-2025",
            "2025-2026",
        ]

    def test_the_overall_line_shows_the_direction(self, faculty_client, three_terms):
        points = faculty_client.get("/reports/me/trend").json()["overall"]

        assert [p["mean"] for p in points] == [3.0, 4.0, 5.0]

    def test_each_point_carries_its_own_sample_size(self, faculty_client, three_terms):
        """A rising line drawn from a shrinking sample is not an improvement,
        and the reader has to be able to see that."""
        points = faculty_client.get("/reports/me/trend").json()["overall"]

        assert all(p["responses"] == 6 for p in points)
        assert all(p["eligible_students"] >= 6 for p in points)
        assert all(p["response_rate"] is not None for p in points)

    def test_criteria_are_trended_because_they_persist_across_terms(
        self, faculty_client, three_terms
    ):
        [series] = faculty_client.get("/reports/me/trend").json()["criteria"]

        assert series["name"] == "Subject knowledge"
        assert [p["mean"] for p in series["points"]] == [3.0, 4.0, 5.0]

    def test_subjects_are_trended_too(self, faculty_client, three_terms):
        [series] = faculty_client.get("/reports/me/trend").json()["subjects"]

        assert series["code"] == "CS3401"
        assert [p["mean"] for p in series["points"]] == [3.0, 4.0, 5.0]

    def test_no_question_level_series_is_offered(self, faculty_client, three_terms):
        """Questions are recreated per term, so joining them across terms would
        mean matching on text — which breaks the first time someone fixes a
        typo. Absent beats wrong."""
        body = faculty_client.get("/reports/me/trend").json()

        assert "questions" not in body


class TestHonesty:
    def test_a_thin_term_contributes_a_gap_not_a_dot(
        self, faculty_client, session, fixtures
    ):
        """Three responses on a chart read as a fact. They are not one."""
        old = make_term(session, "2024-2025", 1, fixtures)
        fill(session, old, fixtures, 5, 3, offset=0)
        fill(session, fixtures["term"], fixtures, 4, 6, offset=100)

        points = faculty_client.get("/reports/me/trend").json()["overall"]
        assert points[0]["mean"] is None
        assert points[0]["responses"] == 3
        assert points[0]["reliability"] == "insufficient"
        assert points[1]["mean"] == 4.0

    def test_a_term_they_did_not_teach_is_omitted_not_zeroed(
        self, faculty_client, session, fixtures
    ):
        """A sabbatical is not a drop in rating, and a line through zero would
        read as one."""
        session.add(
            AcademicTerm(year="2024-2025", semester=1, status=TermStatus.closed)
        )
        session.commit()
        fill(session, fixtures["term"], fixtures, 4, 6)

        body = faculty_client.get("/reports/me/trend").json()
        assert [t["year"] for t in body["terms"]] == ["2025-2026"]

    def test_the_threshold_is_reported_so_a_gap_can_be_explained(
        self, faculty_client, three_terms
    ):
        body = faculty_client.get("/reports/me/trend").json()

        assert body["minimum_responses_for_mean"] == 5

    def test_the_series_is_capped(self, faculty_client, session, fixtures):
        for year in ("2019-2020", "2020-2021", "2021-2022", "2022-2023"):
            term = make_term(session, year, 1, fixtures)
            fill(session, term, fixtures, 4, 6, offset=hash(year) % 900)
        fill(session, fixtures["term"], fixtures, 4, 6, offset=5000)

        body = faculty_client.get("/reports/me/trend", params={"limit": 3}).json()
        assert len(body["terms"]) == 3
        # The most recent three, not the oldest.
        assert body["terms"][-1]["year"] == "2025-2026"


class TestNoData:
    def test_an_instructor_who_has_never_taught_gets_empty_series(
        self, client, session, fixtures
    ):
        """Empty lists rather than an error: somebody newly appointed should
        see "nothing yet", not a failure."""
        newcomer = Account(
            role=Role.faculty,
            first_name="Newly",
            last_name="Appointed",
            email="newcomer@example.edu",
            password_hash=hash_password(PASSWORD),
        )
        session.add(newcomer)
        session.commit()
        client.post(
            "/auth/login", json={"email": newcomer.email, "password": PASSWORD}
        )

        body = client.get("/reports/me/trend").json()
        assert body["faculty_id"] == newcomer.id
        assert body["terms"] == []
        assert body["overall"] == []
        assert body["criteria"] == []
        assert body["subjects"] == []

    def test_a_term_with_no_responses_yields_a_null_mean(
        self, faculty_client, fixtures
    ):
        points = faculty_client.get("/reports/me/trend").json()["overall"]

        assert len(points) == 1
        assert points[0]["mean"] is None
        assert points[0]["responses"] == 0


class TestAccess:
    def test_an_admin_can_see_anyone_s_trend(self, admin_client, three_terms, fixtures):
        response = admin_client.get(
            f"/reports/faculty/{fixtures['faculty'].id}/trend"
        )
        assert response.status_code == 200
        assert [p["mean"] for p in response.json()["overall"]] == [3.0, 4.0, 5.0]

    def test_faculty_cannot_see_another_s_trend(
        self, faculty_client, session, three_terms
    ):
        other = Account(
            role=Role.faculty,
            first_name="Other",
            last_name="Instructor",
            email="other.instructor@example.edu",
            password_hash="placeholder",
        )
        session.add(other)
        session.commit()

        assert (
            faculty_client.get(f"/reports/faculty/{other.id}/trend").status_code == 403
        )

    def test_students_cannot_see_trends(self, student_client, three_terms, fixtures):
        assert (
            student_client.get(
                f"/reports/faculty/{fixtures['faculty'].id}/trend"
            ).status_code
            == 403
        )

    def test_an_anonymous_caller_is_refused(self, client, fixtures):
        assert client.get("/reports/me/trend").status_code == 401

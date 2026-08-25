"""The student submission flow, end to end through the API."""

import pytest

from app.core.security import hash_password
from app.models import (
    Account,
    ClassGroup,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Role,
    TermStatus,
)

PASSWORD = "student-password-here"


def _answers(fixtures, value: int = 5) -> list[dict]:
    return [{"question_id": q.id, "rating": value} for q in fixtures["questions"]]


def _submit(client, fixtures, **overrides):
    payload = {
        "assignment_id": fixtures["assignment"].id,
        "ratings": _answers(fixtures),
    }
    payload.update(overrides)
    return client.post("/evaluations", json=payload)


class TestPendingAssignments:
    def test_a_student_sees_their_class_assignments(self, student_client, fixtures):
        response = student_client.get("/me/assignments/pending")

        assert response.status_code == 200
        [row] = response.json()
        assert row["assignment_id"] == fixtures["assignment"].id
        assert row["faculty_name"] == "Asha Raman"
        assert row["subject_code"] == "CS3401"

    def test_a_submitted_assignment_disappears(self, student_client, fixtures):
        _submit(student_client, fixtures)

        assert student_client.get("/me/assignments/pending").json() == []

    def test_another_class_assignments_are_not_shown(
        self, student_client, session, fixtures
    ):
        other_class = ClassGroup(curriculum="B.E. MECH", level="II", section="C")
        session.add(other_class)
        session.commit()
        fixtures["assignment"].class_group_id = other_class.id
        session.commit()

        assert student_client.get("/me/assignments/pending").json() == []

    def test_faculty_cannot_use_the_student_endpoints(self, client, session, fixtures):
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})

        assert client.get("/me/assignments/pending").status_code == 403


class TestQuestionnaire:
    def test_questions_arrive_grouped_by_criterion(self, student_client, fixtures):
        response = student_client.get("/me/questionnaire")

        assert response.status_code == 200
        body = response.json()
        assert body["term"]["year"] == "2025-2026"
        [block] = body["criteria"]
        assert block["name"] == "Subject knowledge"
        assert len(block["questions"]) == 2


class TestSubmission:
    def test_a_valid_submission_is_recorded(self, student_client, session, fixtures):
        response = _submit(student_client, fixtures)

        assert response.status_code == 201, response.text
        assert response.json()["answers_recorded"] == 2
        assert session.query(EvaluationSubmission).count() == 1
        assert session.query(EvaluationResponse).count() == 1
        assert session.query(EvaluationRating).count() == 2

    def test_the_receipt_does_not_expose_the_response_id(self, student_client, fixtures):
        """Handing back an id for their own anonymous response would give the
        client something to correlate with later."""
        body = _submit(student_client, fixtures).json()

        assert set(body) == {"assignment_id", "answers_recorded"}

    def test_a_second_submission_is_refused(self, student_client, fixtures):
        assert _submit(student_client, fixtures).status_code == 201

        second = _submit(student_client, fixtures)
        assert second.status_code == 409
        assert "already submitted" in second.json()["detail"]

    def test_the_refused_duplicate_leaves_one_response(
        self, student_client, session, fixtures
    ):
        _submit(student_client, fixtures)
        _submit(student_client, fixtures, ratings=_answers(fixtures, 1))

        assert session.query(EvaluationResponse).count() == 1
        assert session.query(EvaluationRating).count() == 2

    def test_a_partial_answer_set_is_refused(self, student_client, session, fixtures):
        """A partial evaluation would quietly skew every mean it feeds."""
        response = _submit(
            student_client, fixtures, ratings=[_answers(fixtures)[0]]
        )

        assert response.status_code == 400
        assert "Every question must be answered" in response.json()["detail"]
        assert session.query(EvaluationSubmission).count() == 0

    def test_an_unknown_question_is_refused(self, student_client, fixtures):
        response = _submit(
            student_client,
            fixtures,
            ratings=[*_answers(fixtures), {"question_id": 999999, "rating": 3}],
        )

        assert response.status_code == 400
        assert "999999" in response.json()["detail"]

    def test_a_repeated_question_is_refused(self, student_client, fixtures):
        first = _answers(fixtures)[0]
        response = _submit(student_client, fixtures, ratings=[first, first])

        assert response.status_code == 422

    @pytest.mark.parametrize("rating", [0, 6, -1])
    def test_ratings_outside_the_legend_are_refused(
        self, student_client, fixtures, rating
    ):
        response = _submit(student_client, fixtures, ratings=_answers(fixtures, rating))

        assert response.status_code == 422

    def test_an_assignment_from_another_class_is_not_found(
        self, student_client, session, fixtures
    ):
        """404 rather than 403, so the response does not confirm it exists."""
        other_class = ClassGroup(curriculum="B.E. MECH", level="II", section="C")
        session.add(other_class)
        session.commit()
        fixtures["assignment"].class_group_id = other_class.id
        session.commit()

        assert _submit(student_client, fixtures).status_code == 404

    def test_submission_before_the_window_opens_is_refused(
        self, student_client, session, fixtures
    ):
        fixtures["term"].status = TermStatus.pending
        session.commit()

        response = _submit(student_client, fixtures)
        assert response.status_code == 409
        assert "not opened" in response.json()["detail"]

    def test_submission_after_the_window_closes_is_refused(
        self, student_client, session, fixtures
    ):
        fixtures["term"].status = TermStatus.closed
        session.commit()

        response = _submit(student_client, fixtures)
        assert response.status_code == 409
        assert "closed" in response.json()["detail"]

    def test_the_student_id_is_never_taken_from_the_request(
        self, student_client, session, fixtures
    ):
        """The legacy form posted student, faculty, class, subject and term as
        hidden fields and trusted all of them."""
        victim = Account(
            role=Role.student,
            first_name="Other",
            last_name="Student",
            email="other.student@example.edu",
            password_hash=hash_password(PASSWORD),
            class_group_id=fixtures["class_group"].id,
        )
        session.add(victim)
        session.commit()

        response = student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": _answers(fixtures),
                "student_id": victim.id,
                "faculty_id": 999,
                "term_id": 999,
            },
        )
        assert response.status_code == 201

        submission = session.query(EvaluationSubmission).one()
        assert submission.student_id == fixtures["student"].id
        assert submission.student_id != victim.id

    def test_an_anonymous_caller_cannot_submit(self, client, fixtures):
        assert _submit(client, fixtures).status_code == 401

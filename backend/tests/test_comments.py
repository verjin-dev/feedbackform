"""Written feedback, and the rules about who may read it.

Ratings are anonymous because the schema makes them so. Prose is not anonymous
in the same way and no schema fixes that, so the protection is procedural.
Every rule below exists because breaking it would put a real student at risk of
being identified, or a real instructor at the wrong end of something that is
not feedback about teaching.
"""

import pytest

from app.core.security import hash_password
from app.models import (
    Account,
    CommentPrompt,
    EvaluationComment,
    EvaluationResponse,
    EvaluationSubmission,
    Role,
    TermStatus,
)

PASSWORD = "a-password-for-tests"


def _student(session, fixtures, n):
    account = Account(
        role=Role.student,
        first_name=f"Student{n}",
        last_name="Extra",
        email=f"student{n}@example.edu",
        password_hash=hash_password(PASSWORD),
        class_group_id=fixtures["class_group"].id,
    )
    session.add(account)
    session.commit()
    return account


def record(session, fixtures, student, *, helped=None, change=None):
    session.add(
        EvaluationSubmission(
            term_id=fixtures["term"].id,
            student_id=student.id,
            assignment_id=fixtures["assignment"].id,
        )
    )
    response = EvaluationResponse(
        term_id=fixtures["term"].id, assignment_id=fixtures["assignment"].id
    )
    session.add(response)
    session.flush()
    if helped:
        session.add(
            EvaluationComment(
                response_id=response.id, prompt=CommentPrompt.helped, text=helped
            )
        )
    if change:
        session.add(
            EvaluationComment(
                response_id=response.id, prompt=CommentPrompt.change, text=change
            )
        )
    session.commit()
    return response


@pytest.fixture
def faculty_client(client, session, fixtures):
    faculty = fixtures["faculty"]
    faculty.password_hash = hash_password(PASSWORD)
    session.commit()
    client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})
    return client


@pytest.fixture
def six_comments(session, fixtures):
    """Enough responses to clear the release threshold."""
    students = [fixtures["student"]] + [_student(session, fixtures, n) for n in range(1, 6)]
    for index, student in enumerate(students):
        record(
            session,
            fixtures,
            student,
            helped=f"The worked examples helped ({index}).",
            change=f"More time on recursion ({index}).",
        )
    return fixtures


def close_window(session, fixtures):
    fixtures["term"].status = TermStatus.closed
    session.commit()


class TestWriting:
    def test_a_student_can_submit_comments_with_their_ratings(
        self, student_client, session, fixtures
    ):
        response = student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
                "comments": [
                    {"prompt": "helped", "text": "The lab sessions."},
                    {"prompt": "change", "text": "Slower pace in week 3."},
                ],
            },
        )

        assert response.status_code == 201
        assert response.json()["comments_recorded"] == 2
        assert session.query(EvaluationComment).count() == 2

    def test_comments_are_optional(self, student_client, session, fixtures):
        """A form that refuses to submit without prose collects worse ratings,
        not better prose."""
        response = student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
            },
        )

        assert response.status_code == 201
        assert response.json()["comments_recorded"] == 0

    def test_blank_comments_are_dropped_rather_than_stored(
        self, student_client, session, fixtures
    ):
        response = student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
                "comments": [
                    {"prompt": "helped", "text": "   "},
                    {"prompt": "change", "text": "Nothing much."},
                ],
            },
        )

        assert response.json()["comments_recorded"] == 1
        assert session.query(EvaluationComment).count() == 1

    def test_a_comment_is_not_linked_to_the_student(
        self, student_client, session, fixtures
    ):
        """It hangs off the anonymous response, like the ratings do."""
        student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
                "comments": [{"prompt": "helped", "text": "The labs."}],
            },
        )

        columns = {c.name for c in EvaluationComment.__table__.columns}
        assert "student_id" not in columns
        assert "submission_id" not in columns

    def test_the_prompts_are_advertised_with_the_questionnaire(
        self, student_client, fixtures
    ):
        prompts = student_client.get("/me/questionnaire").json()["comment_prompts"]

        assert {p["prompt"] for p in prompts} == {"helped", "change"}
        assert all(p["text"].endswith("?") for p in prompts)

    def test_over_length_text_is_refused(self, student_client, fixtures):
        response = student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
                "comments": [{"prompt": "helped", "text": "x" * 2000}],
            },
        )
        assert response.status_code == 422


class TestReleaseRules:
    def test_nothing_is_shown_while_the_window_is_open(
        self, faculty_client, six_comments
    ):
        """An instructor reading criticism while still holding the marking pen
        is a conflict the system should not create."""
        report = faculty_client.get("/reports/me").json()
        assignment = report["assignments"][0]

        assert assignment["comment_state"] == "window_open"
        assert assignment["comments"] == []

    def test_nothing_is_shown_below_the_threshold(
        self, faculty_client, session, fixtures
    ):
        """With three responses, who wrote what is frequently guessable."""
        for n in range(3):
            student = fixtures["student"] if n == 0 else _student(session, fixtures, n)
            record(session, fixtures, student, helped=f"Comment {n}")
        close_window(session, fixtures)

        assignment = faculty_client.get("/reports/me").json()["assignments"][0]
        assert assignment["comment_state"] == "too_few_responses"
        assert assignment["comments"] == []

    def test_comments_appear_once_closed_and_above_the_threshold(
        self, faculty_client, session, six_comments
    ):
        close_window(session, six_comments)

        assignment = faculty_client.get("/reports/me").json()["assignments"][0]
        assert assignment["comment_state"] == "released"
        assert len(assignment["comments"]) == 12
        assert any("worked examples" in c["text"] for c in assignment["comments"])

    def test_an_administrator_can_read_them_before_release(
        self, admin_client, six_comments, fixtures
    ):
        """Somebody has to be able to act on an abusive comment before the
        person it targets ever sees it."""
        report = admin_client.get(
            f"/reports/faculty/{fixtures['faculty'].id}"
        ).json()

        assert report["assignments"][0]["comment_state"] == "released"
        assert len(report["assignments"][0]["comments"]) == 12


class TestModeration:
    def test_a_withheld_comment_never_reaches_the_instructor(
        self, admin_client, client, session, six_comments, fixtures
    ):
        comment_id = admin_client.get("/comments").json()[0]["id"]
        admin_client.post(
            f"/comments/{comment_id}/withhold",
            json={"reason": "Personal remark, not about teaching."},
        )
        close_window(session, fixtures)

        admin_client.post("/auth/logout")
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})

        comments = client.get("/reports/me").json()["assignments"][0]["comments"]
        assert len(comments) == 11
        assert all(comment["id"] != comment_id for comment in comments)

    def test_the_instructor_is_not_told_something_was_withheld(
        self, admin_client, session, six_comments, fixtures
    ):
        """Naming the reason to the person it was about defeats the purpose."""
        comment_id = admin_client.get("/comments").json()[0]["id"]
        admin_client.post(
            f"/comments/{comment_id}/withhold", json={"reason": "Abusive."}
        )
        close_window(session, fixtures)

        # admin_client and faculty_client share one TestClient, so the session
        # is switched rather than a second client being used.
        admin_client.post("/auth/logout")
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        admin_client.post(
            "/auth/login", json={"email": faculty.email, "password": PASSWORD}
        )

        comments = admin_client.get("/reports/me").json()["assignments"][0]["comments"]
        assert comments
        assert all(c.get("withheld_reason") is None for c in comments)

    def test_withholding_records_who_and_why(
        self, admin_client, session, six_comments, admin_account
    ):
        comment_id = admin_client.get("/comments").json()[0]["id"]
        admin_client.post(
            f"/comments/{comment_id}/withhold",
            json={"reason": "Comment about appearance."},
        )

        comment = session.get(EvaluationComment, comment_id)
        assert comment.withheld is True
        assert comment.withheld_reason == "Comment about appearance."
        assert comment.withheld_by_id == admin_account.id
        assert comment.withheld_at is not None

    def test_a_reason_is_required(self, admin_client, six_comments):
        """Moderation without one is indistinguishable from removing criticism
        somebody found inconvenient."""
        comment_id = admin_client.get("/comments").json()[0]["id"]

        response = admin_client.post(
            f"/comments/{comment_id}/withhold", json={"reason": ""}
        )
        assert response.status_code == 422

    def test_withholding_is_reversible(self, admin_client, session, six_comments):
        comment_id = admin_client.get("/comments").json()[0]["id"]
        admin_client.post(f"/comments/{comment_id}/withhold", json={"reason": "Mistake."})

        restored = admin_client.post(f"/comments/{comment_id}/restore")
        assert restored.status_code == 200
        assert restored.json()["withheld"] is False

        session.expire_all()
        assert session.get(EvaluationComment, comment_id).withheld_reason is None

    def test_the_queue_can_be_filtered_to_withheld_only(
        self, admin_client, six_comments
    ):
        comment_id = admin_client.get("/comments").json()[0]["id"]
        admin_client.post(f"/comments/{comment_id}/withhold", json={"reason": "Abusive."})

        withheld = admin_client.get("/comments", params={"withheld": "true"}).json()
        assert [row["id"] for row in withheld] == [comment_id]

    def test_the_queue_names_the_subject_but_never_the_author(
        self, admin_client, six_comments
    ):
        row = admin_client.get("/comments").json()[0]

        assert row["subject_code"] == "CS3401"
        assert row["faculty_name"] == "Asha Raman"
        assert "student" not in row
        assert "author" not in row


class TestAccess:
    def test_faculty_cannot_reach_the_moderation_queue(
        self, faculty_client, six_comments
    ):
        assert faculty_client.get("/comments").status_code == 403

    def test_students_cannot_reach_the_moderation_queue(
        self, student_client, six_comments
    ):
        assert student_client.get("/comments").status_code == 403

    def test_faculty_cannot_withhold(self, admin_client, session, six_comments, fixtures):
        comment_id = admin_client.get("/comments").json()[0]["id"]

        admin_client.post("/auth/logout")
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        admin_client.post(
            "/auth/login", json={"email": faculty.email, "password": PASSWORD}
        )

        assert (
            admin_client.post(
                f"/comments/{comment_id}/withhold", json={"reason": "No."}
            ).status_code
            == 403
        )

    def test_one_faculty_cannot_read_another_s_comments(
        self, faculty_client, session, six_comments
    ):
        other = Account(
            role=Role.faculty,
            first_name="Other",
            last_name="Instructor",
            email="other.instructor@example.edu",
            password_hash=hash_password(PASSWORD),
        )
        session.add(other)
        session.commit()

        assert faculty_client.get(f"/reports/faculty/{other.id}").status_code == 403

"""Reminders, class progress and the scannable code.

Response rate decides whether any of the reporting is worth reading, so the
rules here are about not wasting the one chance to ask: never mail somebody who
has finished, never mail the same person daily, and say what they actually owe.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Account,
    ClassGroup,
    EvaluationResponse,
    EvaluationSubmission,
    ReminderLog,
    Role,
    Subject,
    TeachingAssignment,
)


@pytest.fixture
def cohort(session: Session, fixtures: dict) -> dict:
    """One class, two subjects, three students, nobody has responded."""
    second = Subject(code="CS3402", name="Databases")
    session.add(second)
    session.flush()

    session.add(
        TeachingAssignment(
            term_id=fixtures["term"].id,
            faculty_id=fixtures["faculty"].id,
            class_group_id=fixtures["class_group"].id,
            subject_id=second.id,
        )
    )

    extra = []
    for n in (1, 2):
        account = Account(
            role=Role.student,
            first_name=f"Student{n}",
            last_name="Extra",
            email=f"student{n}@example.edu",
            password_hash=hash_password("a-password-here"),
            class_group_id=fixtures["class_group"].id,
        )
        session.add(account)
        extra.append(account)
    session.commit()

    assignments = (
        session.query(TeachingAssignment)
        .filter_by(term_id=fixtures["term"].id)
        .order_by(TeachingAssignment.id)
        .all()
    )
    return {**fixtures, "students": [fixtures["student"], *extra], "assignments": assignments}


def submit(session: Session, term, student, assignment):
    session.add(
        EvaluationSubmission(
            term_id=term.id, student_id=student.id, assignment_id=assignment.id
        )
    )
    session.add(EvaluationResponse(term_id=term.id, assignment_id=assignment.id))
    session.commit()


class TestOutstanding:
    def test_everyone_starts_outstanding(self, admin_client, cohort):
        response = admin_client.post("/participation/reminders")

        assert response.status_code == 200
        assert response.json()["recipients"] == 3
        assert response.json()["dry_run"] is True

    def test_a_dry_run_sends_nothing(self, admin_client, cohort, outbox):
        admin_client.post("/participation/reminders")

        assert outbox == []

    def test_someone_who_has_finished_is_never_included(
        self, admin_client, session, cohort
    ):
        """A reminder to somebody already done is the fastest way to teach
        people these emails are not worth opening."""
        student = cohort["students"][0]
        for assignment in cohort["assignments"]:
            submit(session, cohort["term"], student, assignment)

        emails = [p["email"] for p in admin_client.post("/participation/reminders").json()["people"]]
        assert student.email not in emails
        assert len(emails) == 2

    def test_someone_partway_through_is_still_reminded(
        self, admin_client, session, cohort
    ):
        student = cohort["students"][0]
        submit(session, cohort["term"], student, cohort["assignments"][0])

        [person] = [
            p
            for p in admin_client.post("/participation/reminders").json()["people"]
            if p["email"] == student.email
        ]
        assert person["outstanding"] == 1

    def test_the_preview_names_the_subjects_owed(self, admin_client, cohort):
        people = admin_client.post("/participation/reminders").json()["people"]

        subjects = people[0]["subjects"]
        assert len(subjects) == 2
        assert any("CS3401" in entry for entry in subjects)
        assert "Asha Raman" in subjects[0]

    def test_it_can_be_narrowed_to_one_class(self, admin_client, session, cohort):
        other = ClassGroup(curriculum="B.E. ECE", level="II", section="B")
        session.add(other)
        session.commit()

        response = admin_client.post(
            "/participation/reminders", params={"class_group_id": other.id}
        )
        assert response.json()["recipients"] == 0

    def test_inactive_students_are_left_alone(self, admin_client, session, cohort):
        cohort["students"][0].is_active = False
        session.commit()

        assert admin_client.post("/participation/reminders").json()["recipients"] == 2


class TestSending:
    def test_sending_writes_one_email_per_person(self, admin_client, cohort, outbox):
        response = admin_client.post(
            "/participation/reminders", params={"dry_run": "false"}
        )

        assert response.json()["recipients"] == 3
        assert len(outbox) == 3

    def test_the_email_lists_what_is_outstanding(self, admin_client, cohort, outbox):
        admin_client.post("/participation/reminders", params={"dry_run": "false"})

        body = outbox[0].body
        assert "CS3401" in body
        assert "CS3402" in body
        assert "/evaluate" in body
        assert "without your name" in body

    def test_the_subject_line_carries_the_count(self, admin_client, cohort, outbox):
        admin_client.post("/participation/reminders", params={"dry_run": "false"})

        assert "2 subjects still to review" in outbox[0].subject

    def test_a_second_run_reminds_nobody(self, admin_client, cohort, outbox):
        """A reminder that arrives daily is a nag, and people who are nagged
        unsubscribe rather than respond."""
        admin_client.post("/participation/reminders", params={"dry_run": "false"})
        outbox.clear()

        second = admin_client.post(
            "/participation/reminders", params={"dry_run": "false"}
        )
        assert second.json()["recipients"] == 0
        assert second.json()["suppressed_by_cooldown"] == 3
        assert outbox == []

    def test_the_cooldown_can_be_overridden_deliberately(
        self, admin_client, cohort, outbox
    ):
        admin_client.post("/participation/reminders", params={"dry_run": "false"})
        outbox.clear()

        again = admin_client.post(
            "/participation/reminders",
            params={"dry_run": "false", "ignore_cooldown": "true"},
        )
        assert again.json()["recipients"] == 3
        assert len(outbox) == 3

    def test_an_old_reminder_does_not_suppress_a_new_one(
        self, admin_client, session, cohort
    ):
        for student in cohort["students"]:
            session.add(
                ReminderLog(
                    term_id=cohort["term"].id,
                    account_id=student.id,
                    sent_at=datetime.now(UTC) - timedelta(days=30),
                )
            )
        session.commit()

        assert admin_client.post("/participation/reminders").json()["recipients"] == 3

    def test_the_preview_distinguishes_held_back_from_finished(
        self, admin_client, cohort
    ):
        """"0 recipients" must not be mistaken for "everyone is done"."""
        admin_client.post("/participation/reminders", params={"dry_run": "false"})

        report = admin_client.post("/participation/reminders").json()
        assert report["recipients"] == 0
        assert report["outstanding_total"] == 3
        assert report["suppressed_by_cooldown"] == 3


class TestProgress:
    def test_a_class_with_nobody_started(self, admin_client, cohort):
        [row] = admin_client.get("/participation/progress").json()

        assert row["students"] == 3
        assert row["assignments"] == 2
        assert row["not_started"] == 3
        assert row["completed"] == 0
        assert row["completion"] == 0.0

    def test_partial_and_complete_are_counted_separately(
        self, admin_client, session, cohort
    ):
        finished, halfway, _ = cohort["students"]
        for assignment in cohort["assignments"]:
            submit(session, cohort["term"], finished, assignment)
        submit(session, cohort["term"], halfway, cohort["assignments"][0])

        [row] = admin_client.get("/participation/progress").json()
        assert row["completed"] == 1
        assert row["partial"] == 1
        assert row["not_started"] == 1
        assert row["completion"] == pytest.approx(1 / 3, abs=0.001)

    def test_a_class_with_no_assignments_is_omitted(self, admin_client, session, cohort):
        """Reporting it as complete would flatter the numbers."""
        session.add(ClassGroup(curriculum="B.E. ECE", level="II", section="B"))
        session.commit()

        labels = [row["label"] for row in admin_client.get("/participation/progress").json()]
        assert labels == ["B.E. CSE III-A"]

    def test_faculty_can_see_progress(self, client, session, cohort):
        """Mentioning it in the room moves the number more than another email."""
        faculty = cohort["faculty"]
        faculty.password_hash = hash_password("faculty-password")
        session.commit()
        client.post(
            "/auth/login",
            json={"email": faculty.email, "password": "faculty-password"},
        )

        assert client.get("/participation/progress").status_code == 200

    def test_students_cannot_see_progress(self, student_client, cohort):
        assert student_client.get("/participation/progress").status_code == 403


class TestQrCode:
    def test_it_returns_a_scannable_svg(self, admin_client, cohort):
        response = admin_client.get("/participation/qr.svg")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert "<svg" in response.text

    def test_students_cannot_fetch_it(self, student_client, cohort):
        assert student_client.get("/participation/qr.svg").status_code == 403


class TestAccess:
    def test_only_admins_can_send_reminders(self, client, session, cohort):
        faculty = cohort["faculty"]
        faculty.password_hash = hash_password("faculty-password")
        session.commit()
        client.post(
            "/auth/login", json={"email": faculty.email, "password": "faculty-password"}
        )

        assert client.post("/participation/reminders").status_code == 403

    def test_an_anonymous_caller_is_refused(self, client, cohort):
        assert client.post("/participation/reminders").status_code == 401
        assert client.get("/participation/progress").status_code == 401

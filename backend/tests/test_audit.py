"""The audit trail, and the things it must never contain.

Recording configuration changes is the easy half. The half that matters is that
this must not become a back door around the anonymity design: an administrator
who can read "student 41 submitted at 14:02" has been handed, in a different
table, exactly what three phases of work removed.
"""


from app.core.security import hash_password
from app.models import (
    AuditEvent,
    CommentPrompt,
    EvaluationComment,
    EvaluationResponse,
    PulseRound,
)

PASSWORD = "audit-password-here"


def events(session, entity_type: str | None = None) -> list[AuditEvent]:
    query = session.query(AuditEvent)
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    return query.order_by(AuditEvent.id).all()


class TestWhatIsRecorded:
    def test_creating_a_subject_is_recorded(self, admin_client, session):
        admin_client.post("/subjects", json={"code": "CS9001", "name": "Compilers"})

        [entry] = events(session, "Subject")
        assert entry.action == "created"
        assert "CS9001" in entry.summary

    def test_the_actor_is_named(self, admin_client, session, admin_account):
        admin_client.post("/subjects", json={"code": "CS9001", "name": "Compilers"})

        [entry] = events(session, "Subject")
        assert entry.actor_id == admin_account.id
        assert entry.actor_email == admin_account.email
        assert entry.actor_name == "Root Admin"

    def test_opening_and_closing_a_window_is_recorded(
        self, admin_client, session, fixtures
    ):
        """The change most likely to be questioned later."""
        admin_client.patch(
            f"/academic-years/{fixtures['term'].id}", json={"status": "closed"}
        )

        [entry] = [e for e in events(session, "AcademicTerm") if e.action == "updated"]
        assert "status" in entry.changes
        assert "closed" in entry.changes

    def test_a_questionnaire_change_is_recorded(self, admin_client, session, fixtures):
        question = fixtures["questions"][0]
        admin_client.patch(
            f"/questions/{question.id}", json={"text": "Reworded mid-term."}
        )

        [entry] = [e for e in events(session, "Question") if e.action == "updated"]
        assert "Reworded mid-term" in entry.changes

    def test_deleting_something_is_recorded(self, admin_client, session):
        created = admin_client.post(
            "/subjects", json={"code": "TMP999", "name": "Temporary"}
        ).json()
        admin_client.delete(f"/subjects/{created['id']}")

        actions = [e.action for e in events(session, "Subject")]
        assert actions == ["created", "deleted"]

    def test_moderation_is_recorded_without_the_comment(
        self, admin_client, session, fixtures
    ):
        response = EvaluationResponse(
            term_id=fixtures["term"].id, assignment_id=fixtures["assignment"].id
        )
        session.add(response)
        session.flush()
        comment = EvaluationComment(
            response_id=response.id,
            prompt=CommentPrompt.change,
            text="Something a student wrote in confidence.",
        )
        session.add(comment)
        session.commit()

        admin_client.post(
            f"/comments/{comment.id}/withhold", json={"reason": "Personal remark."}
        )

        [entry] = [
            e for e in events(session, "EvaluationComment") if e.action == "updated"
        ]
        assert "withheld" in entry.changes
        # The decision is auditable; the text and the reason are not repeated.
        assert "Something a student wrote" not in (entry.changes or "")
        assert "Personal remark" not in (entry.changes or "")

    def test_a_flush_that_changed_nothing_writes_no_row(
        self, admin_client, session, fixtures
    ):
        before = len(events(session))
        admin_client.get("/subjects")
        admin_client.get(f"/academic-years/{fixtures['term'].id}")

        assert len(events(session)) == before


class TestCredentialsAreNeverWritten:
    def test_a_password_change_records_only_that_it_changed(
        self, admin_client, session, fixtures
    ):
        admin_client.patch(
            f"/accounts/{fixtures['student'].id}",
            json={"password": "a-brand-new-secret-value"},
        )

        [entry] = [e for e in events(session, "Account") if e.action == "updated"]
        assert "password_hash: changed" in entry.changes
        assert "a-brand-new-secret-value" not in entry.changes
        assert "argon2" not in entry.changes

    def test_no_hash_reaches_the_log_from_account_creation(
        self, admin_client, session, fixtures
    ):
        admin_client.post(
            "/accounts",
            json={
                "role": "faculty",
                "first_name": "New",
                "last_name": "Person",
                "email": "new.person@example.edu",
                "password": "a-perfectly-fine-password",
            },
        )

        for entry in events(session, "Account"):
            assert "argon2" not in (entry.changes or "")
            assert "a-perfectly-fine-password" not in (entry.changes or "")


class TestItIsNotABackDoor:
    """The anonymity design says no rating, comment or pulse reply can be
    traced to the student who gave it. These make sure this table does not
    quietly reintroduce that."""

    def test_a_submission_writes_no_audit_row(
        self, student_client, session, fixtures
    ):
        student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
                "comments": [{"prompt": "helped", "text": "The lab sessions."}],
            },
        )

        recorded = {e.entity_type for e in events(session)}
        assert "EvaluationSubmission" not in recorded
        assert "EvaluationResponse" not in recorded
        assert "EvaluationRating" not in recorded

    def test_no_student_identity_appears_anywhere_in_the_log(
        self, student_client, session, fixtures
    ):
        student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
            },
        )

        student = fixtures["student"]
        for entry in events(session):
            blob = f"{entry.summary} {entry.changes or ''} {entry.actor_email}"
            assert student.email not in blob

    def test_written_feedback_never_appears_in_the_log(
        self, student_client, session, fixtures
    ):
        student_client.post(
            "/evaluations",
            json={
                "assignment_id": fixtures["assignment"].id,
                "ratings": [
                    {"question_id": q.id, "rating": 4} for q in fixtures["questions"]
                ],
                "comments": [{"prompt": "change", "text": "A distinctive phrase here."}],
            },
        )

        for entry in events(session):
            assert "A distinctive phrase here" not in f"{entry.summary}{entry.changes}"

    def test_the_pulse_is_not_audited_at_all(self, client, session, fixtures):
        """It is not retained past the term, so an audit row would outlive the
        thing it describes."""
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})
        client.post("/pulse/rounds", json={"assignment_id": fixtures["assignment"].id})

        assert session.query(PulseRound).count() == 1
        recorded = {e.entity_type for e in events(session)}
        assert "PulseRound" not in recorded
        assert "PulseReply" not in recorded
        assert "PulseParticipation" not in recorded

    def test_the_log_does_not_audit_itself(self, admin_client, session):
        admin_client.post("/subjects", json={"code": "CS9002", "name": "Networks"})

        assert events(session, "AuditEvent") == []


class TestSurvivingDeletion:
    def test_the_actor_is_still_named_after_their_account_goes(
        self, admin_client, session, fixtures
    ):
        """An audit trail that loses its subject when the account is deleted
        answers the question least well exactly when it is asked most
        urgently."""
        created = admin_client.post(
            "/accounts",
            json={
                "role": "admin",
                "first_name": "Temporary",
                "last_name": "Admin",
                "email": "temp.admin@example.edu",
                "password": "a-password-for-them",
            },
        ).json()

        admin_client.post("/auth/logout")
        admin_client.post(
            "/auth/login",
            json={"email": "temp.admin@example.edu", "password": "a-password-for-them"},
        )
        admin_client.post("/subjects", json={"code": "CS9003", "name": "Graphics"})

        admin_client.post("/auth/logout")
        admin_client.post(
            "/auth/login",
            json={"email": "root.admin@example.edu", "password": "conftest-admin-password"},
        )
        admin_client.delete(f"/accounts/{created['id']}")

        session.expire_all()
        [entry] = [e for e in events(session, "Subject") if "CS9003" in e.summary]
        assert entry.actor_id is None
        assert entry.actor_email == "temp.admin@example.edu"
        assert entry.actor_name == "Temporary Admin"


class TestReading:
    def test_events_come_back_newest_first(self, admin_client):
        admin_client.post("/subjects", json={"code": "AA100", "name": "First"})
        admin_client.post("/subjects", json={"code": "BB200", "name": "Second"})

        rows = admin_client.get("/audit").json()
        assert "BB200" in rows[0]["summary"]

    def test_it_can_be_filtered_by_entity(self, admin_client, fixtures):
        admin_client.post("/subjects", json={"code": "AA100", "name": "First"})
        admin_client.post(
            "/classes", json={"curriculum": "B.E. IT", "level": "I", "section": "A"}
        )

        rows = admin_client.get("/audit", params={"entity_type": "Subject"}).json()
        assert {row["entity_type"] for row in rows} == {"Subject"}

    def test_entity_types_are_listed_for_filtering(self, admin_client):
        admin_client.post("/subjects", json={"code": "AA100", "name": "First"})

        assert "Subject" in admin_client.get("/audit/entity-types").json()

    def test_faculty_cannot_read_the_log(self, client, session, fixtures):
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})

        assert client.get("/audit").status_code == 403

    def test_students_cannot_read_the_log(self, student_client):
        assert student_client.get("/audit").status_code == 403

    def test_an_anonymous_caller_cannot_read_the_log(self, client):
        assert client.get("/audit").status_code == 401

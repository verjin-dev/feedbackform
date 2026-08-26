"""The mid-term check.

Two properties make this worth having, and both have to be real rather than
described: only the instructor sees it, and it does not survive the term. Take
either away and an instructor asks a safe question instead of a useful one.
"""

import pytest

from app.core.security import hash_password
from app.models import (
    Account,
    ClassGroup,
    PulseParticipation,
    PulseReply,
    PulseRound,
    Role,
    Subject,
    TeachingAssignment,
)

PASSWORD = "pulse-password-here"


def student(session, fixtures, n) -> Account:
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


@pytest.fixture
def faculty_client(client, session, fixtures):
    faculty = fixtures["faculty"]
    faculty.password_hash = hash_password(PASSWORD)
    session.commit()
    client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})
    return client


@pytest.fixture
def open_round(faculty_client, fixtures):
    response = faculty_client.post(
        "/pulse/rounds", json={"assignment_id": fixtures["assignment"].id}
    )
    assert response.status_code == 201, response.text
    return response.json()


def sign_in(client, account):
    client.post("/auth/logout")
    client.post("/auth/login", json={"email": account.email, "password": PASSWORD})


def sign_in_admin(client):
    """admin_client and faculty_client wrap the same TestClient, so the session
    belongs to whichever fixture resolved last. Tests that use both switch
    deliberately rather than relying on fixture order."""
    client.post("/auth/logout")
    client.post(
        "/auth/login",
        json={"email": "root.admin@example.edu", "password": "conftest-admin-password"},
    )


def answer(client, round_id, pace=3, clarity=4, suggestion=None):
    return client.post(
        f"/pulse/rounds/{round_id}/reply",
        json={"pace": pace, "clarity": clarity, "suggestion": suggestion},
    )


class TestOpeningAndClosing:
    def test_an_instructor_opens_a_check_on_their_own_subject(
        self, faculty_client, fixtures
    ):
        body = faculty_client.post(
            "/pulse/rounds", json={"assignment_id": fixtures["assignment"].id}
        ).json()

        assert body["is_open"] is True
        assert body["subject_code"] == "CS3401"
        assert body["replies"] == 0

    def test_opening_twice_returns_the_same_round(self, faculty_client, fixtures):
        """Two live checks on one class is a survey, not a pulse."""
        first = faculty_client.post(
            "/pulse/rounds", json={"assignment_id": fixtures["assignment"].id}
        ).json()
        second = faculty_client.post(
            "/pulse/rounds", json={"assignment_id": fixtures["assignment"].id}
        ).json()

        assert first["round_id"] == second["round_id"]

    def test_an_instructor_cannot_open_one_on_somebody_else_s_subject(
        self, faculty_client, session, fixtures
    ):
        other = Account(
            role=Role.faculty,
            first_name="Other",
            last_name="Instructor",
            email="other@example.edu",
            password_hash="placeholder",
        )
        subject = Subject(code="XX100", name="Theirs")
        session.add_all([other, subject])
        session.flush()
        theirs = TeachingAssignment(
            term_id=fixtures["term"].id,
            faculty_id=other.id,
            class_group_id=fixtures["class_group"].id,
            subject_id=subject.id,
        )
        session.add(theirs)
        session.commit()

        response = faculty_client.post("/pulse/rounds", json={"assignment_id": theirs.id})
        # 404 rather than 403: confirming it exists tells one instructor about
        # another's teaching.
        assert response.status_code == 404

    def test_closing_stops_further_replies(
        self, faculty_client, session, fixtures, open_round
    ):
        learner = student(session, fixtures, 1)
        faculty_client.post(f"/pulse/rounds/{open_round['round_id']}/close")

        sign_in(faculty_client, learner)
        assert answer(faculty_client, open_round["round_id"]).status_code == 409

    def test_an_instructor_can_throw_one_away(
        self, faculty_client, session, fixtures, open_round
    ):
        """They own it, which is part of why they can afford to ask something
        uncomfortable."""
        assert (
            faculty_client.delete(f"/pulse/rounds/{open_round['round_id']}").status_code
            == 204
        )
        assert session.query(PulseRound).count() == 0


class TestAnswering:
    def test_a_student_sees_an_open_check_for_their_class(
        self, faculty_client, session, fixtures, open_round
    ):
        learner = student(session, fixtures, 1)
        sign_in(faculty_client, learner)

        [pending] = faculty_client.get("/pulse/pending").json()
        assert pending["round_id"] == open_round["round_id"]
        assert pending["faculty_name"] == "Asha Raman"

    def test_answering_removes_it_from_their_list(
        self, faculty_client, session, fixtures, open_round
    ):
        learner = student(session, fixtures, 1)
        sign_in(faculty_client, learner)

        assert answer(faculty_client, open_round["round_id"]).status_code == 204
        assert faculty_client.get("/pulse/pending").json() == []

    def test_a_second_answer_is_refused(
        self, faculty_client, session, fixtures, open_round
    ):
        learner = student(session, fixtures, 1)
        sign_in(faculty_client, learner)
        answer(faculty_client, open_round["round_id"])

        assert answer(faculty_client, open_round["round_id"]).status_code == 409

    def test_a_student_in_another_class_cannot_answer(
        self, faculty_client, session, fixtures, open_round
    ):
        other_class = ClassGroup(curriculum="B.E. ECE", level="II", section="B")
        session.add(other_class)
        session.commit()
        outsider = Account(
            role=Role.student,
            first_name="Out",
            last_name="Sider",
            email="outsider@example.edu",
            password_hash=hash_password(PASSWORD),
            class_group_id=other_class.id,
        )
        session.add(outsider)
        session.commit()
        sign_in(faculty_client, outsider)

        assert answer(faculty_client, open_round["round_id"]).status_code == 404

    def test_the_reply_is_not_linked_to_the_student(
        self, faculty_client, session, fixtures, open_round
    ):
        """Same split as the end-of-term evaluation."""
        columns = {c.name for c in PulseReply.__table__.columns}
        assert "student_id" not in columns
        assert "participation_id" not in columns

    def test_participation_and_content_stay_in_step(
        self, faculty_client, session, fixtures, open_round
    ):
        for n in range(3):
            learner = student(session, fixtures, n)
            sign_in(faculty_client, learner)
            answer(faculty_client, open_round["round_id"])

        assert session.query(PulseParticipation).count() == 3
        assert session.query(PulseReply).count() == 3

    @pytest.mark.parametrize("pace", [0, 6])
    def test_an_out_of_range_answer_is_refused(
        self, faculty_client, session, fixtures, open_round, pace
    ):
        learner = student(session, fixtures, 1)
        sign_in(faculty_client, learner)

        assert answer(faculty_client, open_round["round_id"], pace=pace).status_code == 422


class TestWhatTheInstructorSees:
    def _three_replies(self, client, session, fixtures, round_id):
        for n, (pace, clarity, note) in enumerate(
            [(4, 3, "Slow down on recursion."), (5, 2, None), (3, 5, "More examples.")]
        ):
            learner = student(session, fixtures, n)
            sign_in(client, learner)
            answer(client, round_id, pace=pace, clarity=clarity, suggestion=note)

    def test_nothing_is_shown_below_three_replies(
        self, faculty_client, session, fixtures, open_round
    ):
        learner = student(session, fixtures, 1)
        sign_in(faculty_client, learner)
        answer(faculty_client, open_round["round_id"], suggestion="Only me here.")

        sign_in(faculty_client, fixtures["faculty"])
        [summary] = faculty_client.get("/pulse/mine").json()

        assert summary["replies"] == 1
        assert summary["released"] is False
        assert summary["suggestions"] == []
        assert summary["clarity_mean"] is None

    def test_results_appear_once_enough_have_answered(
        self, faculty_client, session, fixtures, open_round
    ):
        self._three_replies(faculty_client, session, fixtures, open_round["round_id"])
        sign_in(faculty_client, fixtures["faculty"])

        [summary] = faculty_client.get("/pulse/mine").json()
        assert summary["released"] is True
        assert summary["replies"] == 3
        assert summary["clarity_mean"] == pytest.approx(3.33, abs=0.01)
        assert sorted(summary["suggestions"]) == [
            "More examples.",
            "Slow down on recursion.",
        ]

    def test_pace_is_reported_as_a_spread_not_a_score(
        self, faculty_client, session, fixtures, open_round
    ):
        """There is no good end of the pace scale, so it is counts rather than
        an average that would sit meaninglessly near the middle."""
        self._three_replies(faculty_client, session, fixtures, open_round["round_id"])
        sign_in(faculty_client, fixtures["faculty"])

        [summary] = faculty_client.get("/pulse/mine").json()
        assert summary["pace_counts"]["4"] == 1
        assert summary["pace_counts"]["5"] == 1
        assert summary["pace_counts"]["3"] == 1
        assert "pace_mean" not in summary


class TestItIsNotAnEvaluation:
    def test_a_pulse_never_reaches_the_faculty_report(
        self, faculty_client, session, fixtures, open_round
    ):
        for n in range(3):
            learner = student(session, fixtures, n)
            sign_in(faculty_client, learner)
            answer(faculty_client, open_round["round_id"], suggestion=f"Note {n}")

        sign_in(faculty_client, fixtures["faculty"])
        report = faculty_client.get("/reports/me").json()

        assignment = report["assignments"][0]
        assert assignment["responses"] == 0
        assert assignment["mean"] is None
        assert "Note 0" not in faculty_client.get("/reports/me").text

    def test_a_pulse_never_reaches_the_accreditation_export(
        self, admin_client, faculty_client, session, fixtures, open_round
    ):
        for n in range(3):
            learner = student(session, fixtures, n)
            sign_in(faculty_client, learner)
            answer(faculty_client, open_round["round_id"], suggestion=f"Secret {n}")

        sign_in(faculty_client, fixtures["faculty"])
        # Back to the administrator to pull the export.
        faculty_client.post("/auth/logout")
        admin_client.post(
            "/auth/login",
            json={"email": "root.admin@example.edu", "password": "conftest-admin-password"},
        )
        body = admin_client.get("/exports/results.csv").text

        assert "Secret" not in body
        # Participation is the end-of-term figure, untouched by the pulse.
        assert "0" in admin_client.get("/exports/participation.csv").text


class TestAdministratorsCannotRead:
    def test_there_is_no_route_to_another_person_s_pulse(self, admin_client, open_round):
        paths = admin_client.get("/openapi.json").json()["paths"]

        assert "/pulse/mine" in paths
        assert not any(
            "pulse" in path and "{faculty_id}" in path for path in paths
        )

    def test_an_administrator_sees_counts_only(
        self, admin_client, faculty_client, session, fixtures, open_round
    ):
        learner = student(session, fixtures, 1)
        sign_in(faculty_client, learner)
        answer(faculty_client, open_round["round_id"], suggestion="Please slow down.")

        faculty_client.post("/auth/logout")
        admin_client.post(
            "/auth/login",
            json={"email": "root.admin@example.edu", "password": "conftest-admin-password"},
        )
        activity = admin_client.get("/pulse/activity")

        assert activity.status_code == 200
        assert activity.json() == {"rounds_open": 1, "rounds_total": 1, "replies": 1}
        assert "Please slow down" not in activity.text

    def test_an_administrator_cannot_list_pulse_results(self, admin_client, open_round):
        sign_in_admin(admin_client)

        assert admin_client.get("/pulse/mine").status_code == 403

    def test_a_student_cannot_read_results(
        self, faculty_client, session, fixtures, open_round
    ):
        learner = student(session, fixtures, 1)
        sign_in(faculty_client, learner)

        assert faculty_client.get("/pulse/mine").status_code == 403
        assert faculty_client.get("/pulse/activity").status_code == 403


class TestRetention:
    def test_closing_the_term_deletes_every_pulse(
        self, admin_client, faculty_client, session, fixtures, open_round
    ):
        """"Formative, not retained" is a promise that has to be kept in code."""
        for n in range(3):
            learner = student(session, fixtures, n)
            sign_in(faculty_client, learner)
            answer(faculty_client, open_round["round_id"], suggestion=f"Note {n}")

        faculty_client.post("/auth/logout")
        admin_client.post(
            "/auth/login",
            json={"email": "root.admin@example.edu", "password": "conftest-admin-password"},
        )
        closed = admin_client.patch(
            f"/academic-years/{fixtures['term'].id}", json={"status": "closed"}
        )
        assert closed.status_code == 200

        session.expire_all()
        assert session.query(PulseRound).count() == 0
        assert session.query(PulseReply).count() == 0
        assert session.query(PulseParticipation).count() == 0

    def test_the_end_of_term_evaluation_survives_that_purge(
        self, admin_client, session, fixtures, open_round
    ):
        """Only the pulse goes. The evaluation is the record."""
        from app.models import EvaluationResponse, EvaluationSubmission

        session.add(
            EvaluationSubmission(
                term_id=fixtures["term"].id,
                student_id=fixtures["student"].id,
                assignment_id=fixtures["assignment"].id,
            )
        )
        session.add(
            EvaluationResponse(
                term_id=fixtures["term"].id, assignment_id=fixtures["assignment"].id
            )
        )
        session.commit()

        sign_in_admin(admin_client)
        admin_client.patch(
            f"/academic-years/{fixtures['term'].id}", json={"status": "closed"}
        )

        session.expire_all()
        assert session.query(EvaluationSubmission).count() == 1
        assert session.query(EvaluationResponse).count() == 1

    def test_reopening_a_closed_term_does_not_resurrect_anything(
        self, admin_client, fixtures, session, open_round
    ):
        sign_in_admin(admin_client)
        admin_client.patch(
            f"/academic-years/{fixtures['term'].id}", json={"status": "closed"}
        )
        admin_client.patch(
            f"/academic-years/{fixtures['term'].id}", json={"status": "open"}
        )

        session.expire_all()
        assert session.query(PulseRound).count() == 0

    def test_a_status_change_that_is_not_closing_leaves_it_alone(
        self, admin_client, fixtures, session, open_round
    ):
        sign_in_admin(admin_client)
        admin_client.patch(
            f"/academic-years/{fixtures['term'].id}", json={"status": "pending"}
        )

        session.expire_all()
        assert session.query(PulseRound).count() == 1

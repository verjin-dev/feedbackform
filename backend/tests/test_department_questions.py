"""Department-scoped questions.

A question can be asked of the whole college or of one department. The risk
this creates is not in asking the questions -- it is in the report: a
questionnaire resolved for the wrong department prints another department's
questions with zero counts, which on the page is indistinguishable from a
question nobody answered. Most of what follows is about that.
"""

from app.core.security import hash_password
from app.models import (
    Account,
    ClassGroup,
    Question,
    Role,
    TeachingAssignment,
)
from app.services.reporting import (
    assignment_reports,
    normalise_curriculum,
    questionnaire_for,
    term_questionnaire,
)

PASSWORD = "department-password"


def add_question(session, fixtures, text, curriculum=None, position=9):
    question = Question(
        term_id=fixtures["term"].id,
        criterion_id=fixtures["criterion"].id,
        text=text,
        position=position,
        curriculum=curriculum,
    )
    session.add(question)
    session.commit()
    return question


def add_department(session, fixtures, curriculum, section="A"):
    """A second class in another department, with its own student and an
    assignment against the same faculty member."""
    group = ClassGroup(curriculum=curriculum, level="III", section=section)
    session.add(group)
    session.flush()

    slug = "".join(ch for ch in curriculum.lower() if ch.isalnum())
    student = Account(
        role=Role.student,
        school_id=f"S-{slug[:6]}-{section}",
        first_name="Other",
        last_name="Student",
        email=f"other.{slug}@example.edu",
        password_hash=hash_password(PASSWORD),
        class_group_id=group.id,
    )
    assignment = TeachingAssignment(
        term_id=fixtures["term"].id,
        faculty_id=fixtures["faculty"].id,
        class_group_id=group.id,
        subject_id=fixtures["subject"].id,
    )
    session.add_all([student, assignment])
    session.commit()
    return {"class_group": group, "student": student, "assignment": assignment}


def sign_in(client, email):
    client.post("/auth/logout")
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def question_texts(questionnaire):
    return [q.text for _, questions in questionnaire for q in questions]


class TestResolution:
    def test_a_question_without_a_curriculum_is_asked_of_everyone(
        self, session, fixtures
    ):
        add_question(session, fixtures, "Shared question.")

        for curriculum in ("B.E. CSE", "B.E. Mechanical", None):
            texts = question_texts(
                questionnaire_for(session, fixtures["term"].id, curriculum)
            )
            assert "Shared question." in texts

    def test_a_department_question_reaches_only_that_department(
        self, session, fixtures
    ):
        add_question(
            session,
            fixtures,
            "Lab safety briefing was adequate.",
            curriculum="B.E. Mechanical",
        )

        mechanical = question_texts(
            questionnaire_for(session, fixtures["term"].id, "B.E. Mechanical")
        )
        cse = question_texts(questionnaire_for(session, fixtures["term"].id, "B.E. CSE"))

        assert "Lab safety briefing was adequate." in mechanical
        assert "Lab safety briefing was adequate." not in cse

    def test_spelling_variants_of_a_department_still_match(self, session, fixtures):
        """The legacy data holds three spellings of one department. A silently
        dropped block is a question the student is never asked and nobody
        notices was missing."""
        add_question(session, fixtures, "Departmental question.", curriculum="B.E. IT")

        for spelling in ("B.E. IT", "b.e. it", "  B.E.   IT  "):
            texts = question_texts(
                questionnaire_for(session, fixtures["term"].id, spelling)
            )
            assert "Departmental question." in texts, spelling

    def test_a_different_department_is_not_matched_by_a_prefix(self, session, fixtures):
        add_question(session, fixtures, "IT only.", curriculum="B.E. IT")

        texts = question_texts(
            questionnaire_for(session, fixtures["term"].id, "B.E. ITX")
        )
        assert "IT only." not in texts

    def test_core_questions_come_before_the_department_block(self, session, fixtures):
        add_question(
            session, fixtures, "Department addition.", curriculum="B.E. CSE", position=1
        )
        add_question(session, fixtures, "Shared addition.", position=8)

        texts = question_texts(
            questionnaire_for(session, fixtures["term"].id, "B.E. CSE")
        )
        assert texts.index("Shared addition.") < texts.index("Department addition.")

    def test_the_admin_view_shows_every_department(self, session, fixtures):
        add_question(
            session, fixtures, "Mechanical only.", curriculum="B.E. Mechanical"
        )
        add_question(session, fixtures, "CSE only.", curriculum="B.E. CSE")

        texts = question_texts(term_questionnaire(session, fixtures["term"].id))
        assert "Mechanical only." in texts
        assert "CSE only." in texts

    def test_normalise_treats_blank_as_no_department(self):
        assert normalise_curriculum("   ") is None
        assert normalise_curriculum(None) is None


class TestTheReportIsShapedPerDepartment:
    def test_another_departments_question_is_absent_not_zero(self, session, fixtures):
        """The failure this design exists to prevent.

        A questionnaire resolved once for the whole term would print the
        Mechanical question against the CSE assignment with counts of zero,
        which reads on the page as "nobody answered it" rather than "it was
        never asked".
        """
        add_question(
            session, fixtures, "Mechanical only.", curriculum="B.E. Mechanical"
        )
        add_department(session, fixtures, "B.E. Mechanical")

        reports = assignment_reports(session, fixtures["term"])
        by_class = {r["curriculum"]: r for r in reports}

        cse_questions = [
            q["text"] for c in by_class["B.E. CSE"]["criteria"] for q in c["questions"]
        ]
        mech_questions = [
            q["text"]
            for c in by_class["B.E. Mechanical"]["criteria"]
            for q in c["questions"]
        ]

        assert "Mechanical only." not in cse_questions
        assert "Mechanical only." in mech_questions

    def test_a_question_report_says_which_department_answered_it(
        self, session, fixtures
    ):
        add_question(session, fixtures, "CSE only.", curriculum="B.E. CSE")

        [report] = assignment_reports(session, fixtures["term"])
        scopes = {
            q["text"]: q["curriculum"]
            for c in report["criteria"]
            for q in c["questions"]
        }
        assert scopes["CSE only."] == "B.E. CSE"
        assert scopes["Explains concepts clearly."] is None

    def test_a_term_with_no_department_questions_reports_as_before(
        self, session, fixtures
    ):
        add_department(session, fixtures, "B.E. Mechanical")

        for report in assignment_reports(session, fixtures["term"]):
            texts = [q["text"] for c in report["criteria"] for q in c["questions"]]
            assert texts == [
                "Explains concepts clearly.",
                "Answers questions thoroughly.",
            ]


class TestTheStudentFlow:
    def sign_in_student(self, client, session, fixtures):
        student = fixtures["student"]
        student.password_hash = hash_password(PASSWORD)
        session.commit()
        return sign_in(client, student.email)

    def test_the_form_holds_the_core_plus_their_own_block(
        self, client, session, fixtures
    ):
        add_question(session, fixtures, "CSE only.", curriculum="B.E. CSE")
        add_question(
            session, fixtures, "Mechanical only.", curriculum="B.E. Mechanical"
        )
        self.sign_in_student(client, session, fixtures)

        body = client.get("/me/questionnaire").json()
        texts = [q["text"] for c in body["criteria"] for q in c["questions"]]

        assert "CSE only." in texts
        assert "Mechanical only." not in texts

    def test_answering_exactly_what_was_shown_is_accepted(
        self, client, session, fixtures
    ):
        """The set the form is drawn from and the set the submission is checked
        against are resolved the same way, so a student cannot be told a
        question is missing that they were never shown."""
        add_question(session, fixtures, "CSE only.", curriculum="B.E. CSE")
        add_question(
            session, fixtures, "Mechanical only.", curriculum="B.E. Mechanical"
        )
        self.sign_in_student(client, session, fixtures)

        shown = client.get("/me/questionnaire").json()
        ratings = [
            {"question_id": q["id"], "rating": 4}
            for c in shown["criteria"]
            for q in c["questions"]
        ]
        response = client.post(
            "/evaluations",
            json={"assignment_id": fixtures["assignment"].id, "ratings": ratings},
        )
        assert response.status_code == 201, response.text

    def test_answering_another_departments_question_is_rejected(
        self, client, session, fixtures
    ):
        foreign = add_question(
            session, fixtures, "Mechanical only.", curriculum="B.E. Mechanical"
        )
        self.sign_in_student(client, session, fixtures)

        ratings = [{"question_id": q.id, "rating": 4} for q in fixtures["questions"]]
        ratings.append({"question_id": foreign.id, "rating": 5})

        response = client.post(
            "/evaluations",
            json={"assignment_id": fixtures["assignment"].id, "ratings": ratings},
        )
        assert response.status_code == 400
        assert "Not part of this questionnaire" in response.json()["detail"]


class TestEditing:
    def test_a_question_can_be_scoped_to_a_department(self, admin_client, fixtures):
        response = admin_client.post(
            "/questions",
            json={
                "term_id": fixtures["term"].id,
                "criterion_id": fixtures["criterion"].id,
                "text": "Lab equipment was available.",
                "curriculum": "B.E. CSE",
            },
        )
        assert response.status_code == 201
        assert response.json()["curriculum"] == "B.E. CSE"

    def test_a_department_nobody_is_enrolled_in_is_rejected(
        self, admin_client, fixtures
    ):
        """Scoped to a typo, the question is asked of nobody, looks correct on
        the questionnaire screen, and is simply absent from every report."""
        response = admin_client.post(
            "/questions",
            json={
                "term_id": fixtures["term"].id,
                "criterion_id": fixtures["criterion"].id,
                "text": "Never asked of anybody.",
                "curriculum": "B.E. Astrology",
            },
        )
        assert response.status_code == 422
        assert "B.E. Astrology" in response.json()["detail"]

    def test_the_spelling_used_by_the_classes_is_the_one_stored(
        self, admin_client, fixtures
    ):
        response = admin_client.post(
            "/questions",
            json={
                "term_id": fixtures["term"].id,
                "criterion_id": fixtures["criterion"].id,
                "text": "Typed casually.",
                "curriculum": "b.e.   cse ",
            },
        )
        assert response.json()["curriculum"] == "B.E. CSE"

    def test_a_department_question_can_be_returned_to_the_core(
        self, admin_client, session, fixtures
    ):
        question = add_question(
            session, fixtures, "Was departmental.", curriculum="B.E. CSE"
        )

        response = admin_client.patch(
            f"/questions/{question.id}", json={"curriculum": None}
        )
        assert response.json()["curriculum"] is None

    def test_omitting_the_field_leaves_the_scope_alone(
        self, admin_client, session, fixtures
    ):
        question = add_question(
            session, fixtures, "Departmental.", curriculum="B.E. CSE"
        )

        response = admin_client.patch(
            f"/questions/{question.id}", json={"text": "Reworded."}
        )
        assert response.json()["curriculum"] == "B.E. CSE"

    def test_the_departments_list_comes_from_the_classes(
        self, admin_client, session, fixtures
    ):
        add_department(session, fixtures, "B.E. Mechanical")

        assert admin_client.get("/questions/departments").json() == [
            "B.E. CSE",
            "B.E. Mechanical",
        ]


class TestCarryingAQuestionnaireForward:
    def new_term(self, admin_client):
        return admin_client.post(
            "/academic-years", json={"year": "2026-2027", "semester": 1}
        ).json()

    def test_it_copies_the_core_and_the_department_blocks(
        self, admin_client, session, fixtures
    ):
        add_question(session, fixtures, "CSE only.", curriculum="B.E. CSE")
        target = self.new_term(admin_client)

        copied = admin_client.post(
            "/questions/copy",
            json={
                "source_term_id": fixtures["term"].id,
                "target_term_id": target["id"],
            },
        ).json()

        assert {q["text"] for q in copied} == {
            "Explains concepts clearly.",
            "Answers questions thoroughly.",
            "CSE only.",
        }
        assert {q["curriculum"] for q in copied} == {None, "B.E. CSE"}
        assert all(q["term_id"] == target["id"] for q in copied)

    def test_the_originals_are_untouched(self, admin_client, session, fixtures):
        target = self.new_term(admin_client)
        admin_client.post(
            "/questions/copy",
            json={
                "source_term_id": fixtures["term"].id,
                "target_term_id": target["id"],
            },
        )

        still_there = admin_client.get(
            "/questions", params={"term_id": fixtures["term"].id}
        ).json()
        assert len(still_there) == 2

    def test_copying_a_term_onto_itself_is_refused(self, admin_client, fixtures):
        response = admin_client.post(
            "/questions/copy",
            json={
                "source_term_id": fixtures["term"].id,
                "target_term_id": fixtures["term"].id,
            },
        )
        assert response.status_code == 422

    def test_copying_from_an_empty_term_says_so(self, admin_client, fixtures):
        source = self.new_term(admin_client)
        target = admin_client.post(
            "/academic-years", json={"year": "2027-2028", "semester": 1}
        ).json()

        response = admin_client.post(
            "/questions/copy",
            json={"source_term_id": source["id"], "target_term_id": target["id"]},
        )
        assert response.status_code == 404

    def test_a_second_copy_is_refused(self, admin_client, fixtures):
        """Merging would duplicate questions students then answer twice;
        emptying the target for them would discard work nobody asked to
        discard."""
        target = self.new_term(admin_client)
        first = admin_client.post(
            "/questions/copy",
            json={
                "source_term_id": fixtures["term"].id,
                "target_term_id": target["id"],
            },
        )
        assert first.status_code == 200

        second = admin_client.post(
            "/questions/copy",
            json={
                "source_term_id": fixtures["term"].id,
                "target_term_id": target["id"],
            },
        )
        assert second.status_code == 409

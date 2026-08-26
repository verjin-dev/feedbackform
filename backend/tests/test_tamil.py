"""Tamil alongside English on the student-facing surface.

The scope is deliberate and worth stating: students are asked to say something
candid about their teacher, and asking that in a language somebody is merely
competent in gets a shorter, blander answer than asking it in the language they
think in. Staff reports and the accreditation exports stay in English.

Two kinds of text are involved. Interface text ships with the application.
Question wording belongs to the college and is entered per question -- so the
behaviour that matters most here is the fallback: an untranslated question must
appear in English, never disappear.
"""

from app.core import i18n
from app.core.security import hash_password
from app.models import Question

PASSWORD = "tamil-password-here"

TAMIL_QUESTION = "கருத்துகளைத் தெளிவாக விளக்குகிறார்."
TAMIL_CRITERION = "பாட அறிவு"


def sign_in_student(client, session, fixtures):
    student = fixtures["student"]
    student.password_hash = hash_password(PASSWORD)
    session.commit()
    client.post("/auth/login", json={"email": student.email, "password": PASSWORD})
    return student


def questionnaire_texts(client) -> list[str]:
    body = client.get("/me/questionnaire").json()
    return [q["text"] for c in body["criteria"] for q in c["questions"]]


class TestNormalising:
    def test_an_unknown_language_reads_as_english(self):
        """The worst case is a student seeing English and switching again,
        which is not worth an error page mid-form."""
        assert i18n.normalise("fr") == "en"
        assert i18n.normalise("") == "en"
        assert i18n.normalise(None) == "en"

    def test_a_regional_variant_maps_to_its_language(self):
        assert i18n.normalise("ta-IN") == "ta"
        assert i18n.normalise("EN-GB") == "en"

    def test_tamil_is_offered_under_its_own_name(self):
        assert i18n.LANGUAGE_NAMES["ta"] == "தமிழ்"


class TestChoosingALanguage:
    def test_a_new_account_reads_in_english(self, client, session, fixtures):
        student = sign_in_student(client, session, fixtures)
        assert student.language == "en"
        assert client.get("/auth/me").json()["language"] == "en"

    def test_the_choice_is_stored_on_the_account(self, client, session, fixtures):
        """Not in the browser: students share lab machines, and a preference
        that follows the machine rather than the person keeps being wrong."""
        student = sign_in_student(client, session, fixtures)

        response = client.post("/auth/me/language", json={"language": "ta"})
        assert response.status_code == 200
        assert response.json()["language"] == "ta"

        session.expire_all()
        assert session.get(type(student), student.id).language == "ta"

    def test_it_survives_signing_out_and_back_in(self, client, session, fixtures):
        sign_in_student(client, session, fixtures)
        client.post("/auth/me/language", json={"language": "ta"})

        client.post("/auth/logout")
        client.post(
            "/auth/login",
            json={"email": fixtures["student"].email, "password": PASSWORD},
        )
        assert client.get("/auth/me").json()["language"] == "ta"

    def test_an_unsupported_language_is_stored_as_english(
        self, client, session, fixtures
    ):
        sign_in_student(client, session, fixtures)

        response = client.post("/auth/me/language", json={"language": "de"})
        assert response.json()["language"] == "en"

    def test_the_offered_languages_are_listed_for_the_sign_in_page(self, client):
        codes = {row["code"]: row["name"] for row in client.get("/auth/languages").json()}
        assert codes == {"en": "English", "ta": "தமிழ்"}


class TestTheQuestionnaire:
    def translate(self, session, fixtures):
        question = fixtures["questions"][0]
        question.text_ta = TAMIL_QUESTION
        fixtures["criterion"].name_ta = TAMIL_CRITERION
        session.commit()
        return question

    def test_english_is_unchanged_for_a_reader_who_did_not_switch(
        self, client, session, fixtures
    ):
        self.translate(session, fixtures)
        sign_in_student(client, session, fixtures)

        assert questionnaire_texts(client) == [
            "Explains concepts clearly.",
            "Answers questions thoroughly.",
        ]

    def test_a_tamil_reader_gets_the_tamil_wording(self, client, session, fixtures):
        self.translate(session, fixtures)
        sign_in_student(client, session, fixtures)
        client.post("/auth/me/language", json={"language": "ta"})

        assert TAMIL_QUESTION in questionnaire_texts(client)

    def test_an_untranslated_question_falls_back_rather_than_vanishing(
        self, client, session, fixtures
    ):
        """The behaviour the whole design turns on. A half-translated
        questionnaire is readable; one where the untranslated questions
        disappear is a different questionnaire, quietly."""
        self.translate(session, fixtures)
        sign_in_student(client, session, fixtures)
        client.post("/auth/me/language", json={"language": "ta"})

        texts = questionnaire_texts(client)
        assert len(texts) == 2
        assert "Answers questions thoroughly." in texts

    def test_an_empty_translation_is_treated_as_no_translation(
        self, client, session, fixtures
    ):
        question = fixtures["questions"][0]
        question.text_ta = ""
        session.commit()

        sign_in_student(client, session, fixtures)
        client.post("/auth/me/language", json={"language": "ta"})

        assert "Explains concepts clearly." in questionnaire_texts(client)

    def test_the_criterion_heading_is_translated_too(
        self, client, session, fixtures
    ):
        self.translate(session, fixtures)
        sign_in_student(client, session, fixtures)
        client.post("/auth/me/language", json={"language": "ta"})

        body = client.get("/me/questionnaire").json()
        assert body["criteria"][0]["name"] == TAMIL_CRITERION

    def test_the_response_says_which_language_it_is_in(
        self, client, session, fixtures
    ):
        """The interface needs it to set `lang` on the form: Tamil inside an
        element declared English is read by a screen reader with English
        phonetics, which is unintelligible rather than merely wrong."""
        sign_in_student(client, session, fixtures)
        assert client.get("/me/questionnaire").json()["language"] == "en"

        client.post("/auth/me/language", json={"language": "ta"})
        assert client.get("/me/questionnaire").json()["language"] == "ta"

    def test_the_written_prompts_are_translated(self, client, session, fixtures):
        sign_in_student(client, session, fixtures)
        client.post("/auth/me/language", json={"language": "ta"})

        body = client.get("/me/questionnaire").json()
        prompts = {row["prompt"]: row["text"] for row in body["comment_prompts"]}
        assert prompts["helped"] == i18n.COMMENT_PROMPTS["helped"]["ta"]
        assert "?" in prompts["change"]

    def test_the_question_ids_do_not_change_with_the_language(
        self, client, session, fixtures
    ):
        """A submission is checked against ids, so a translation that changed
        them would reject a form the student had just been shown."""
        self.translate(session, fixtures)
        sign_in_student(client, session, fixtures)

        english = client.get("/me/questionnaire").json()
        client.post("/auth/me/language", json={"language": "ta"})
        tamil = client.get("/me/questionnaire").json()

        def ids(body):
            return [q["id"] for c in body["criteria"] for q in c["questions"]]

        assert ids(english) == ids(tamil)

    def test_a_tamil_reader_can_submit(self, client, session, fixtures):
        self.translate(session, fixtures)
        sign_in_student(client, session, fixtures)
        client.post("/auth/me/language", json={"language": "ta"})

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


class TestEnteringTheWording:
    def test_an_administrator_can_supply_the_tamil(self, admin_client, fixtures):
        response = admin_client.patch(
            f"/questions/{fixtures['questions'][0].id}",
            json={"text_ta": TAMIL_QUESTION},
        )
        assert response.status_code == 200
        assert response.json()["text_ta"] == TAMIL_QUESTION

    def test_a_question_can_be_created_with_both_wordings(
        self, admin_client, fixtures
    ):
        response = admin_client.post(
            "/questions",
            json={
                "term_id": fixtures["term"].id,
                "criterion_id": fixtures["criterion"].id,
                "text": "Returns marked work promptly.",
                "text_ta": TAMIL_QUESTION,
            },
        )
        assert response.status_code == 201
        assert response.json()["text_ta"] == TAMIL_QUESTION

    def test_carrying_a_questionnaire_forward_carries_the_tamil(
        self, admin_client, session, fixtures
    ):
        """Retyping the Tamil each term is worse than retyping the English:
        fewer people at the college can check it."""
        question = fixtures["questions"][0]
        question.text_ta = TAMIL_QUESTION
        session.commit()

        target = admin_client.post(
            "/academic-years", json={"year": "2026-2027", "semester": 1}
        ).json()
        copied = admin_client.post(
            "/questions/copy",
            json={
                "source_term_id": fixtures["term"].id,
                "target_term_id": target["id"],
            },
        ).json()

        assert TAMIL_QUESTION in {q["text_ta"] for q in copied}


class TestTheStaffSurfaceStaysInEnglish:
    def test_the_report_holds_the_english_wording(
        self, client, session, fixtures
    ):
        """Reports and the accreditation return are read by staff and by
        assessors, in the language the institution conducts that work in.
        Switching them with a student's preference would mean two people
        looking at the same report saw different text."""
        question = fixtures["questions"][0]
        question.text_ta = TAMIL_QUESTION
        session.commit()

        from app.services.reporting import assignment_reports

        [report] = assignment_reports(session, fixtures["term"])
        texts = [q["text"] for c in report["criteria"] for q in c["questions"]]
        assert "Explains concepts clearly." in texts
        assert TAMIL_QUESTION not in texts

    def test_the_export_holds_the_english_wording(self, session, fixtures):
        question = session.get(Question, fixtures["questions"][0].id)
        question.text_ta = TAMIL_QUESTION
        session.commit()

        from app.services.exporting import questionnaire_csv

        body = questionnaire_csv(session, fixtures["term"])
        assert "Explains concepts clearly." in body
        assert TAMIL_QUESTION not in body

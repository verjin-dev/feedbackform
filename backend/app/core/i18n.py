"""The two languages the student-facing surface is offered in.

Scope is deliberate. Students are asked to say something candid about their
teacher, and asking that in a language somebody is merely competent in gets a
shorter, blander answer than asking it in the language they think in. Staff
reports, the admin screens and the accreditation exports stay in English,
which is the language the institution already conducts that work in.

Two kinds of text are involved and they are handled differently:

  - Interface text -- buttons, headings, validation -- ships with the
    application and is translated here and in the frontend dictionary.
  - Question wording and criterion headings belong to the college, not to the
    application. They are entered per question and fall back to English until
    somebody supplies the Tamil. A half-translated questionnaire is readable;
    one where untranslated questions disappear is not.
"""

ENGLISH = "en"
TAMIL = "ta"

SUPPORTED = (ENGLISH, TAMIL)

# Shown in the language it names, not in the reader's current one: somebody
# looking for Tamil is looking for the word "தமிழ்".
LANGUAGE_NAMES = {
    ENGLISH: "English",
    TAMIL: "தமிழ்",
}


def normalise(language: str | None) -> str:
    """Anything unrecognised reads as English rather than failing.

    A stored preference that no longer maps to a supported language must not
    take the form down; the worst case is a student seeing English and
    switching back.
    """
    if language is None:
        return ENGLISH
    code = language.strip().lower().split("-")[0]
    return code if code in SUPPORTED else ENGLISH


# --- Server-owned strings ---------------------------------------------------
#
# Only text the API itself puts in front of a student belongs here. Everything
# the interface says for itself lives in the frontend dictionary, so a wording
# change does not need a deployment of both halves.
#
# The Tamil below is written to be read by a first-year student, not to be
# formally correct: "மதிப்பீடு" over rarer registers, and the polite plural
# throughout. It should be reviewed by a Tamil speaker at the college before
# it goes in front of anybody -- these are translations of the application's
# words, not the college's.

COMMENT_PROMPTS = {
    "helped": {
        ENGLISH: "What helped you learn in this subject?",
        TAMIL: "இந்தப் பாடத்தைக் கற்க உங்களுக்கு எது உதவியது?",
    },
    "change": {
        ENGLISH: "What would you change?",
        TAMIL: "நீங்கள் எதை மாற்ற விரும்புகிறீர்கள்?",
    },
}


def comment_prompt(prompt: str, language: str) -> str:
    wording = COMMENT_PROMPTS.get(prompt)
    if wording is None:
        return prompt
    return wording.get(normalise(language)) or wording[ENGLISH]

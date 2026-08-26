from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CommentPrompt, TermStatus


class TermBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: str
    semester: int
    status: TermStatus


class PendingAssignmentOut(BaseModel):
    """One instructor-and-subject a student still has to rate."""

    assignment_id: int
    faculty_id: int
    faculty_name: str
    subject_id: int
    subject_code: str
    subject_name: str


class QuestionBrief(BaseModel):
    id: int
    text: str


class CriterionBlock(BaseModel):
    criterion_id: int
    name: str
    questions: list[QuestionBrief]


class CommentPromptOut(BaseModel):
    prompt: CommentPrompt
    text: str


class QuestionnaireOut(BaseModel):
    term: TermBrief

    # Which language this came back in, after normalising. The interface needs
    # it to set `lang` on the form: Tamil text inside an element declared
    # English is read by a screen reader with English phonetics, which is
    # unintelligible rather than merely wrong.
    language: str = "en"

    criteria: list[CriterionBlock]
    comment_prompts: list[CommentPromptOut] = Field(default_factory=list)


class RatingIn(BaseModel):
    question_id: int
    rating: int = Field(ge=1, le=5)


class CommentIn(BaseModel):
    prompt: CommentPrompt
    text: str = Field(max_length=1500)


class EvaluationSubmitRequest(BaseModel):
    """Only the assignment and the answers.

    The legacy form posted class_id, faculty_id, subject_id, academic_id and
    restriction_id as hidden fields, every one of them attacker-controlled and
    trusted on arrival. Everything except the answers is now derived from the
    assignment and the session.
    """

    assignment_id: int
    ratings: list[RatingIn] = Field(min_length=1)

    # Optional. Written feedback is the most useful thing a student can give
    # and the most effort to give, so it is never required — a form that
    # refuses to submit without prose collects worse ratings, not better prose.
    comments: list[CommentIn] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def one_answer_per_question(self) -> "EvaluationSubmitRequest":
        question_ids = [rating.question_id for rating in self.ratings]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("A question was answered more than once.")
        return self


class SubmissionReceipt(BaseModel):
    """Deliberately returns no response id.

    Handing the client an identifier for its own anonymous response would give
    it something to correlate later. There is nothing the student needs to do
    with it.
    """

    assignment_id: int
    answers_recorded: int
    comments_recorded: int = 0

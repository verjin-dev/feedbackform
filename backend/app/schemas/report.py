from pydantic import BaseModel

from app.schemas.evaluation import TermBrief


class QuestionReport(BaseModel):
    question_id: int
    text: str

    # Keyed "1".."5". Always all five keys, including zeros.
    counts: dict[str, int]
    percentages: dict[str, float]

    responses: int

    # None, not 0.0, when nothing was answered. A question nobody rated is not
    # a question rated zero, and the legacy report dropped such questions from
    # the output entirely — so a sparse criterion read as a complete one.
    mean: float | None


class CriterionReport(BaseModel):
    criterion_id: int
    name: str
    questions: list[QuestionReport]
    mean: float | None


class AssignmentReport(BaseModel):
    assignment_id: int
    subject_id: int
    subject_code: str
    subject_name: str
    class_group_id: int
    class_label: str

    eligible_students: int
    responses: int
    response_rate: float | None

    criteria: list[CriterionReport]
    mean: float | None


class FacultyReport(BaseModel):
    faculty_id: int
    faculty_name: str
    term: TermBrief
    assignments: list[AssignmentReport]
    mean: float | None


class ResponseRateRow(BaseModel):
    assignment_id: int
    faculty_id: int
    faculty_name: str
    subject_code: str
    class_label: str
    eligible_students: int
    responses: int
    response_rate: float | None


class ResponseRateReport(BaseModel):
    term: TermBrief
    rows: list[ResponseRateRow]
    eligible_students: int
    responses: int
    response_rate: float | None

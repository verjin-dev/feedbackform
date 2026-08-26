from pydantic import BaseModel

from app.schemas.evaluation import TermBrief


class QuestionReport(BaseModel):
    question_id: int
    text: str

    # None where the whole college answered it; a curriculum where only that
    # department did. A department block and the shared core are not the same
    # population, and a reader comparing two faculty needs to see which is
    # which before reading anything into the difference.
    curriculum: str | None = None

    # Keyed "1".."5". Always all five keys, including zeros.
    counts: dict[str, int]
    percentages: dict[str, float]

    responses: int

    # None in two distinct cases, both meaning "no figure to publish":
    # nothing was answered, or too few people answered for a mean to be honest.
    # `reliability` and `responses` tell them apart. A question nobody rated is
    # not a question rated zero, and the legacy report dropped such questions
    # from the output entirely — so a sparse criterion read as a complete one.
    mean: float | None

    # 95% interval for the mean, clamped to the 1-5 scale. Present only when a
    # mean is published; its width is the point.
    mean_range: tuple[float, float] | None = None

    # "insufficient" | "low" | "adequate"
    reliability: str = "insufficient"


class CriterionReport(BaseModel):
    criterion_id: int
    name: str
    questions: list[QuestionReport]
    mean: float | None


class CommentOut(BaseModel):
    id: int
    prompt: str
    text: str
    withheld: bool = False
    # Only ever populated for an administrator; a faculty member is not told
    # that something about them was taken down, or why.
    withheld_reason: str | None = None


class CohortBand(BaseModel):
    """The middle half of what comparable subjects scored.

    Deliberately carries no names, no ids, no position and no percentile — a
    percentile is a ranking with one row visible.
    """

    size: int
    p25: float
    median: float
    p75: float
    basis: str


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
    reliability: str = "insufficient"

    criteria: list[CriterionReport]
    mean: float | None

    # None where there is no honest comparison to draw: too few comparable
    # subjects, or too few of them with a published mean.
    cohort: CohortBand | None = None

    comments: list[CommentOut] = []
    # "released" | "window_open" | "too_few_responses" — why prose is or is not
    # being shown, so the page can say which rather than showing an empty list.
    comment_state: str = "released"
    comment_total: int = 0


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


class TrendPoint(BaseModel):
    term_id: int
    label: str
    # None where too few responded that term. A gap in the line is the honest
    # rendering; a dot would be read as a fact.
    mean: float | None
    responses: int
    eligible_students: int
    response_rate: float | None
    reliability: str


class TrendSeries(BaseModel):
    name: str
    points: list[TrendPoint]


class CriterionTrend(TrendSeries):
    criterion_id: int


class SubjectTrend(BaseModel):
    subject_id: int
    code: str
    name: str
    points: list[TrendPoint]


class TermRef(BaseModel):
    id: int
    year: str
    semester: int
    label: str


class FacultyTrend(BaseModel):
    faculty_id: int
    faculty_name: str
    terms: list[TermRef]
    overall: list[TrendPoint]
    criteria: list[CriterionTrend]
    subjects: list[SubjectTrend]
    minimum_responses_for_mean: int

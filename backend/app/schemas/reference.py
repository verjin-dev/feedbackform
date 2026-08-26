from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TermStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Academic terms --------------------------------------------------------


class AcademicTermCreate(BaseModel):
    year: str = Field(min_length=4, max_length=20, examples=["2025-2026"])
    semester: int = Field(ge=1, le=4)
    status: TermStatus = TermStatus.pending

    @field_validator("year")
    @classmethod
    def strip_year(cls, value: str) -> str:
        return value.strip()


class AcademicTermUpdate(BaseModel):
    year: str | None = Field(default=None, min_length=4, max_length=20)
    semester: int | None = Field(default=None, ge=1, le=4)
    status: TermStatus | None = None


class AcademicTermOut(ORMModel):
    id: int
    year: str
    semester: int
    status: TermStatus
    is_current: bool


# --- Classes ---------------------------------------------------------------


class ClassGroupCreate(BaseModel):
    curriculum: str = Field(min_length=1, max_length=100)
    level: str = Field(min_length=1, max_length=50)
    section: str = Field(min_length=1, max_length=50)


class ClassGroupUpdate(BaseModel):
    curriculum: str | None = Field(default=None, min_length=1, max_length=100)
    level: str | None = Field(default=None, min_length=1, max_length=50)
    section: str | None = Field(default=None, min_length=1, max_length=50)


class ClassGroupOut(ORMModel):
    id: int
    curriculum: str
    level: str
    section: str
    label: str


# --- Subjects --------------------------------------------------------------


class SubjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class SubjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class SubjectOut(ORMModel):
    id: int
    code: str
    name: str
    description: str | None


# --- Criteria --------------------------------------------------------------


class CriterionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CriterionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class CriterionOut(ORMModel):
    id: int
    name: str
    position: int


# --- Questions -------------------------------------------------------------


class QuestionCreate(BaseModel):
    term_id: int
    criterion_id: int
    text: str = Field(min_length=1)

    # Omitted or null asks it of the whole college. A curriculum asks it only
    # of that department.
    curriculum: str | None = Field(default=None, max_length=100)


class QuestionUpdate(BaseModel):
    criterion_id: int | None = None
    text: str | None = Field(default=None, min_length=1)

    # Present-and-null moves a department question back into the core, so the
    # route reads model_fields_set rather than treating null as "unchanged".
    curriculum: str | None = Field(default=None, max_length=100)


class QuestionOut(ORMModel):
    id: int
    term_id: int
    criterion_id: int
    text: str
    position: int
    curriculum: str | None = None


class QuestionnaireCopyRequest(BaseModel):
    """Carry a term's questionnaire forward instead of retyping it.

    Retyping was the practical reason questionnaires drifted between terms, and
    a questionnaire that changed wording without anyone deciding to change it
    makes the term-on-term trend meaningless.
    """

    source_term_id: int
    target_term_id: int


# --- Ordering --------------------------------------------------------------


class ReorderRequest(BaseModel):
    """Whole-list reorder.

    The legacy endpoints wrote one position per request, so an interrupted
    drag left the list inconsistent. This replaces the entire ordering in a
    single transaction, and the ids must be exactly the set being ordered —
    a partial list is rejected rather than silently leaving gaps.
    """

    ids: list[int] = Field(min_length=1)

    @field_validator("ids")
    @classmethod
    def no_duplicates(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("ids must not contain duplicates")
        return value

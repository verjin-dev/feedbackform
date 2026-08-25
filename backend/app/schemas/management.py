from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import Role


class AccountCreate(BaseModel):
    """Fields are enumerated explicitly.

    The legacy save_user looped over every POST key into `SET $k='$v'`, so any
    column in the table was writable by anyone who named it. Nothing outside
    this list can be set through the API.
    """

    role: Role
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    school_id: str | None = Field(default=None, max_length=50)
    class_group_id: int | None = None

    @model_validator(mode="after")
    def students_need_a_class(self) -> "AccountCreate":
        if self.role is Role.student and self.class_group_id is None:
            raise ValueError("A student account must belong to a class.")
        return self


class AccountUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)
    school_id: str | None = Field(default=None, max_length=50)
    class_group_id: int | None = None
    is_active: bool | None = None
    # Role is deliberately absent: changing what an account *is* mid-life is a
    # separate, auditable operation, not a field edit.


class AssignmentItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    faculty_id: int
    class_group_id: int
    subject_id: int


class AssignmentReplaceRequest(BaseModel):
    """The full set of assignments for a term.

    Replaces rather than patches, because that is how the admin screen works:
    the matrix is edited as a whole and saved once.
    """

    assignments: list[AssignmentItem]

    @model_validator(mode="after")
    def no_duplicates(self) -> "AssignmentReplaceRequest":
        if len(set(self.assignments)) != len(self.assignments):
            raise ValueError("The same assignment appears more than once.")
        return self


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term_id: int
    faculty_id: int
    faculty_name: str
    class_group_id: int
    class_label: str
    subject_id: int
    subject_code: str
    subject_name: str

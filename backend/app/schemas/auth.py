from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Role


class LoginRequest(BaseModel):
    """The legacy form also sent a `login` field selecting which table to
    authenticate against. It is gone: the role comes from the account."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Role
    school_id: str | None
    first_name: str
    last_name: str
    full_name: str
    email: EmailStr
    class_group_id: int | None
    avatar: str | None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=256)


class TokenCheck(BaseModel):
    """Lets the page say "this link has expired" before someone types a new
    password into a form that is going to reject it."""

    valid: bool
    email: str | None = None
    first_name: str | None = None

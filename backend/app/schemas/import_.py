from pydantic import BaseModel


class ImportRowOut(BaseModel):
    line: int
    action: str
    email: str
    name: str
    role: str
    messages: list[str]
    # Present only for rows that will be created without a supplied password.
    # Shown once, in the result, so the administrator can distribute it. This
    # goes away when invitation emails exist.
    generated_password: str | None = None


class ImportReportOut(BaseModel):
    dry_run: bool
    file_errors: list[str]
    total: int
    created: int
    updated: int
    skipped: int
    errors: int
    ok: bool
    rows: list[ImportRowOut]

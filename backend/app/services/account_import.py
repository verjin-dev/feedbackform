"""Bulk account import from a CSV file.

Adding several hundred students through a modal, one at a time, is the kind of
task that quietly does not get done — and a class that never got entered is a
silent zero in every response rate it touches.

Two passes, and the order matters. The file is validated in full and reported
on before anything is written, so an administrator sees every problem at once
rather than fixing them one failed upload at a time. A dry run is the default:
writing requires asking for it.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
import string
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Account, ClassGroup, Role

# Accepted column names. Spreadsheets arrive with whatever heading the person
# typed, so a few obvious spellings map onto each field rather than rejecting
# the file over "Email Address".
COLUMN_ALIASES = {
    "role": {"role", "type", "account_type"},
    "first_name": {"first_name", "firstname", "first name", "given_name", "name"},
    "last_name": {"last_name", "lastname", "last name", "surname"},
    "email": {"email", "email_address", "email address", "mail"},
    "school_id": {"school_id", "roll", "roll_no", "roll number", "staff_id", "register_no"},
    "password": {"password", "initial_password"},
    "curriculum": {"curriculum", "programme", "program", "course", "branch"},
    "level": {"level", "year", "semester_level"},
    "section": {"section", "sec"},
}

REQUIRED = ("role", "first_name", "last_name", "email")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Generated when a row carries no password. Returned in the result so the
# administrator can distribute them; once outbound email exists this should
# become an invitation link instead, and these should stop being shown at all.
PASSWORD_ALPHABET = string.ascii_letters + string.digits


def generate_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(14))


@dataclass
class RowResult:
    line: int
    action: str  # "create" | "update" | "skip" | "error"
    email: str = ""
    name: str = ""
    role: str = ""
    messages: list[str] = field(default_factory=list)
    # Only populated for rows that will be created without a supplied password.
    generated_password: str | None = None


@dataclass
class ImportReport:
    dry_run: bool
    rows: list[RowResult] = field(default_factory=list)
    file_errors: list[str] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(1 for row in self.rows if row.action == "create")

    @property
    def updated(self) -> int:
        return sum(1 for row in self.rows if row.action == "update")

    @property
    def skipped(self) -> int:
        return sum(1 for row in self.rows if row.action == "skip")

    @property
    def errors(self) -> int:
        return sum(1 for row in self.rows if row.action == "error")

    @property
    def ok(self) -> bool:
        return not self.file_errors and self.errors == 0


def _normalise_headers(fieldnames: list[str] | None) -> dict[str, str]:
    """Maps the file's actual headings onto our field names."""
    mapping: dict[str, str] = {}
    for raw in fieldnames or []:
        key = raw.strip().lower().replace("-", "_")
        for field_name, aliases in COLUMN_ALIASES.items():
            if key in aliases:
                mapping[raw] = field_name
                break
    return mapping


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """Returns (rows, file-level errors). Rows keep their 1-based line number."""
    errors: list[str] = []

    try:
        # utf-8-sig: Excel writes a byte-order mark that would otherwise become
        # part of the first column's name and break every heading match.
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError:
            return [], ["The file is not readable as UTF-8 or Windows-1252 text."]

    reader = csv.DictReader(io.StringIO(text))
    mapping = _normalise_headers(reader.fieldnames)

    recognised = set(mapping.values())
    missing = [name for name in REQUIRED if name not in recognised]
    if missing:
        errors.append(
            "The file is missing required columns: "
            + ", ".join(missing)
            + ". Found: "
            + (", ".join(reader.fieldnames or []) or "nothing")
        )
        return [], errors

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        # reader.line_num, not a counter: DictReader silently drops blank rows
        # without yielding them, and a quoted field can span lines. Counting
        # iterations reports a number that does not match what the person sees
        # in their spreadsheet, which is worse than no number at all.
        row = {"__line": str(reader.line_num)}
        for raw_key, value in raw_row.items():
            field_name = mapping.get(raw_key)
            if field_name:
                row[field_name] = _clean(value)
        # Skip entirely blank lines rather than reporting them as errors.
        if any(value for key, value in row.items() if key != "__line"):
            rows.append(row)

    if not rows:
        errors.append("The file has a valid header but no data rows.")

    return rows, errors


def build_report(
    db: Session,
    content: bytes,
    *,
    dry_run: bool = True,
    on_existing: str = "skip",
    invite: bool = True,
) -> ImportReport:
    rows, file_errors = parse(content)
    report = ImportReport(dry_run=dry_run, file_errors=file_errors)
    if file_errors:
        return report

    # Existing state, read once.
    existing_emails = {
        email.lower(): account_id
        for account_id, email in db.execute(select(Account.id, Account.email)).all()
    }
    existing_school_ids = {
        school_id
        for (school_id,) in db.execute(
            select(Account.school_id).where(Account.school_id.is_not(None))
        ).all()
    }
    classes = {
        (
            group.curriculum.strip().lower(),
            group.level.strip().lower(),
            group.section.strip().lower(),
        ): group
        for group in db.scalars(select(ClassGroup)).all()
    }

    seen_emails: dict[str, int] = {}
    seen_school_ids: dict[str, int] = {}

    for row in rows:
        line = int(row["__line"])
        result = RowResult(line=line, action="error")
        messages: list[str] = []

        role_text = row.get("role", "").lower()
        email = row.get("email", "").lower()
        first = row.get("first_name", "")
        last = row.get("last_name", "")
        school_id = row.get("school_id", "")

        result.email = email
        result.name = f"{first} {last}".strip()
        result.role = role_text

        try:
            role = Role(role_text)
        except ValueError:
            messages.append(
                f"Role must be admin, faculty or student — got '{row.get('role', '')}'."
            )
            role = None  # type: ignore[assignment]

        if not first:
            messages.append("First name is required.")
        if not last:
            messages.append("Last name is required.")
        if not email:
            messages.append("Email is required.")
        elif not EMAIL_PATTERN.match(email):
            messages.append(f"'{email}' is not a valid email address.")

        # Duplicates inside the file are reported against the later row, so the
        # first occurrence still imports.
        if email and email in seen_emails:
            messages.append(f"Duplicate of line {seen_emails[email]} in this file.")
        elif email:
            seen_emails[email] = line

        if school_id:
            if school_id in seen_school_ids:
                messages.append(
                    f"Institutional id '{school_id}' also appears on line "
                    f"{seen_school_ids[school_id]}."
                )
            else:
                seen_school_ids[school_id] = line

        group: ClassGroup | None = None
        if role is Role.student:
            key = (
                row.get("curriculum", "").lower(),
                row.get("level", "").lower(),
                row.get("section", "").lower(),
            )
            if not all(key):
                messages.append(
                    "Students need curriculum, level and section so they can be "
                    "placed in a class."
                )
            else:
                group = classes.get(key)
                if group is None:
                    messages.append(
                        f"No class matches {row.get('curriculum')} / "
                        f"{row.get('level')} / {row.get('section')}. Create it first."
                    )

        already = existing_emails.get(email) if email else None

        if messages:
            result.messages = messages
            report.rows.append(result)
            continue

        if already is not None:
            if on_existing == "update":
                result.action = "update"
                result.messages = ["Existing account — name and class will be updated."]
            else:
                result.action = "skip"
                result.messages = ["Already registered; left unchanged."]
            report.rows.append(result)
            continue

        if school_id and school_id in existing_school_ids:
            result.messages = [
                f"Institutional id '{school_id}' already belongs to another account."
            ]
            report.rows.append(result)
            continue

        result.action = "create"
        # A generated password is only shown when there is no other way to hand
        # the account over. With invitations on, the person sets their own and
        # nothing needs to be printed, copied or passed along.
        if not invite and not row.get("password"):
            result.generated_password = generate_password()
        report.rows.append(result)

    return report


def apply(
    db: Session,
    content: bytes,
    report: ImportReport,
    *,
    on_existing: str = "skip",
) -> list[Account]:
    """Writes the rows the report marked create or update.

    Called only after build_report found no errors, and in one transaction:
    a partial roll is worse than none, because the gap is invisible. Returns
    the accounts created, so the caller can invite them.
    """
    rows, _ = parse(content)
    by_line = {int(row["__line"]): row for row in rows}
    decisions = {row.line: row for row in report.rows}

    classes = {
        (
            group.curriculum.strip().lower(),
            group.level.strip().lower(),
            group.section.strip().lower(),
        ): group
        for group in db.scalars(select(ClassGroup)).all()
    }

    created: list[Account] = []

    for line, decision in sorted(decisions.items()):
        if decision.action not in ("create", "update"):
            continue
        row = by_line[line]
        role = Role(row["role"].lower())
        email = row["email"].lower()

        group = None
        if role is Role.student:
            group = classes[
                (
                    row.get("curriculum", "").lower(),
                    row.get("level", "").lower(),
                    row.get("section", "").lower(),
                )
            ]

        if decision.action == "update":
            account = db.scalar(
                select(Account).where(func.lower(Account.email) == email)
            )
            if account is None:
                continue
            account.first_name = row["first_name"]
            account.last_name = row["last_name"]
            if row.get("school_id"):
                account.school_id = row["school_id"]
            if group is not None:
                account.class_group_id = group.id
            continue

        # Every account gets a real credential even when it is never told to
        # anyone: a random one that nobody knows is strictly better than a
        # placeholder, and the invitation link is what makes it usable.
        password = row.get("password") or decision.generated_password or generate_password()
        account = Account(
            role=role,
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=email,
            school_id=row.get("school_id") or None,
            password_hash=hash_password(password),
            class_group_id=group.id if group else None,
        )
        db.add(account)
        created.append(account)

    db.commit()
    for account in created:
        db.refresh(account)
    return created

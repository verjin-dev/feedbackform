"""Who has not responded yet, and how to reach them.

Response rate is the variable that decides whether anything else in the
reporting is worth reading. A well-designed report on an 18% response rate is
a well-designed guess.

Everything here is about lowering the cost of responding rather than raising
the volume of asking: one reminder that names the subjects actually
outstanding, a progress view a tutor can put on a projector, and a code people
can scan from their seat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    ClassGroup,
    EvaluationSubmission,
    ReminderLog,
    Role,
    TeachingAssignment,
)

# A reminder that arrives daily is a nag, and people who are nagged unsubscribe
# rather than respond.
DEFAULT_COOLDOWN_DAYS = 3


@dataclass
class Outstanding:
    account: Account
    subjects: list[str] = field(default_factory=list)
    last_reminded: datetime | None = None

    @property
    def outstanding_count(self) -> int:
        return len(self.subjects)


@dataclass
class ClassProgress:
    class_group_id: int
    label: str
    students: int
    completed: int  # answered every subject assigned to them
    partial: int  # answered some
    not_started: int
    assignments: int  # subjects each student is expected to rate

    @property
    def completion(self) -> float | None:
        if self.students == 0:
            return None
        return round(self.completed / self.students, 4)


def _assignments_by_class(db: Session, term: AcademicTerm) -> dict[int, list[TeachingAssignment]]:
    grouped: dict[int, list[TeachingAssignment]] = {}
    for assignment in db.scalars(
        select(TeachingAssignment).where(TeachingAssignment.term_id == term.id)
    ).unique():
        grouped.setdefault(assignment.class_group_id, []).append(assignment)
    return grouped


def _submitted_by_student(db: Session, term: AcademicTerm) -> dict[int, set[int]]:
    """student id -> the assignment ids they have already rated."""
    result: dict[int, set[int]] = {}
    for student_id, assignment_id in db.execute(
        select(EvaluationSubmission.student_id, EvaluationSubmission.assignment_id).where(
            EvaluationSubmission.term_id == term.id
        )
    ).all():
        result.setdefault(student_id, set()).add(assignment_id)
    return result


def _last_reminded(db: Session, term: AcademicTerm) -> dict[int, datetime]:
    rows = db.execute(
        select(ReminderLog.account_id, func.max(ReminderLog.sent_at))
        .where(ReminderLog.term_id == term.id)
        .group_by(ReminderLog.account_id)
    ).all()
    return {account_id: sent_at for account_id, sent_at in rows}


def find_outstanding(
    db: Session,
    term: AcademicTerm,
    *,
    class_group_id: int | None = None,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
    ignore_cooldown: bool = False,
) -> list[Outstanding]:
    """Active students with at least one subject still to rate.

    A student with nothing outstanding is never included: a reminder to
    somebody who has already finished is the fastest way to teach people that
    these emails are not worth opening.
    """
    by_class = _assignments_by_class(db, term)
    submitted = _submitted_by_student(db, term)
    reminded = _last_reminded(db, term)
    cutoff = datetime.now(UTC) - timedelta(days=cooldown_days)

    statement = select(Account).where(
        Account.role == Role.student,
        Account.is_active.is_(True),
        Account.class_group_id.is_not(None),
    )
    if class_group_id is not None:
        statement = statement.where(Account.class_group_id == class_group_id)

    results: list[Outstanding] = []
    for student in db.scalars(statement.order_by(Account.last_name, Account.first_name)):
        assignments = by_class.get(student.class_group_id or 0, [])
        done = submitted.get(student.id, set())
        pending = [a for a in assignments if a.id not in done]
        if not pending:
            continue

        last = reminded.get(student.id)
        if not ignore_cooldown and last is not None:
            # SQLite hands back naive datetimes; treat them as UTC.
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            if last > cutoff:
                continue

        results.append(
            Outstanding(
                account=student,
                subjects=[
                    f"{a.subject.code} — {a.subject.name} ({a.faculty.full_name})"
                    for a in pending
                ],
                last_reminded=last,
            )
        )
    return results


def class_progress(db: Session, term: AcademicTerm) -> list[ClassProgress]:
    by_class = _assignments_by_class(db, term)
    submitted = _submitted_by_student(db, term)

    students_by_class: dict[int, list[Account]] = {}
    for student in db.scalars(
        select(Account).where(
            Account.role == Role.student,
            Account.is_active.is_(True),
            Account.class_group_id.is_not(None),
        )
    ):
        students_by_class.setdefault(student.class_group_id or 0, []).append(student)

    rows: list[ClassProgress] = []
    for group in db.scalars(select(ClassGroup).order_by(ClassGroup.curriculum, ClassGroup.level, ClassGroup.section)):
        assignments = by_class.get(group.id, [])
        students = students_by_class.get(group.id, [])

        # A class with no assignments has nothing to complete; reporting it as
        # 100% done would flatter the numbers.
        if not assignments:
            continue

        expected = len(assignments)
        completed = partial = not_started = 0
        for student in students:
            done = len(submitted.get(student.id, set()) & {a.id for a in assignments})
            if done == 0:
                not_started += 1
            elif done >= expected:
                completed += 1
            else:
                partial += 1

        rows.append(
            ClassProgress(
                class_group_id=group.id,
                label=group.label,
                students=len(students),
                completed=completed,
                partial=partial,
                not_started=not_started,
                assignments=expected,
            )
        )
    return rows


def record_reminders(db: Session, term: AcademicTerm, accounts: list[Account]) -> None:
    for account in accounts:
        db.add(ReminderLog(term_id=term.id, account_id=account.id))
    db.commit()

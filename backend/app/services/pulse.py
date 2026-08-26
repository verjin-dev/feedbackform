"""The mid-term check.

Everything here is scoped by one rule: a pulse is a note an instructor asked
for, not evidence about them. It never reaches a report, an export, a cohort
band or a trend, and it is deleted when the term closes.

That is not squeamishness. An instructor who thinks a mid-term question might
be quoted back at them in a review will ask a safe one, or not ask at all, and
a safe question produces nothing worth having.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    PulseParticipation,
    PulseReply,
    PulseRound,
    Role,
    TeachingAssignment,
)

MAX_SUGGESTION_LENGTH = 600

# Below this, replies are not shown at all — the same disclosure reasoning as
# the end-of-term comments, and it matters more here because a mid-term class
# is small and still meeting.
MIN_REPLIES_TO_SHOW = 3

PACE_LABELS = {
    1: "Much too slow",
    2: "A little slow",
    3: "About right",
    4: "A little fast",
    5: "Much too fast",
}


@dataclass
class RoundSummary:
    round_id: int
    assignment_id: int
    subject_code: str
    subject_name: str
    class_label: str
    is_open: bool
    opened_at: datetime
    closed_at: datetime | None
    eligible: int
    replies: int
    released: bool
    pace_counts: dict[int, int]
    clarity_mean: float | None
    suggestions: list[str]


def _eligible_students(db: Session, assignment: TeachingAssignment) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Account)
            .where(
                Account.role == Role.student,
                Account.is_active.is_(True),
                Account.class_group_id == assignment.class_group_id,
            )
        )
        or 0
    )


def summarise(db: Session, round_: PulseRound) -> RoundSummary:
    replies = db.scalars(
        select(PulseReply).where(PulseReply.round_id == round_.id)
    ).all()

    pace_counts = dict.fromkeys(range(1, 6), 0)
    clarity_values: list[int] = []
    suggestions: list[str] = []
    for reply in replies:
        pace_counts[reply.pace] = pace_counts.get(reply.pace, 0) + 1
        clarity_values.append(reply.clarity)
        if reply.suggestion:
            suggestions.append(reply.suggestion)

    released = len(replies) >= MIN_REPLIES_TO_SHOW

    return RoundSummary(
        round_id=round_.id,
        assignment_id=round_.assignment_id,
        subject_code=round_.assignment.subject.code,
        subject_name=round_.assignment.subject.name,
        class_label=round_.assignment.class_group.label,
        is_open=round_.is_open,
        opened_at=round_.opened_at,
        closed_at=round_.closed_at,
        eligible=_eligible_students(db, round_.assignment),
        replies=len(replies),
        released=released,
        pace_counts=pace_counts if released else dict.fromkeys(range(1, 6), 0),
        clarity_mean=(
            round(sum(clarity_values) / len(clarity_values), 2)
            if released and clarity_values
            else None
        ),
        suggestions=suggestions if released else [],
    )


def open_round(db: Session, assignment: TeachingAssignment) -> PulseRound:
    """One open round per subject at a time.

    Two live checks on the same class is a survey, not a pulse, and the second
    one is where response rates go to die.
    """
    existing = db.scalar(
        select(PulseRound).where(
            PulseRound.assignment_id == assignment.id,
            PulseRound.closed_at.is_(None),
        )
    )
    if existing is not None:
        return existing

    round_ = PulseRound(assignment_id=assignment.id)
    db.add(round_)
    db.commit()
    db.refresh(round_)
    return round_


def close_round(db: Session, round_: PulseRound) -> PulseRound:
    if round_.closed_at is None:
        round_.closed_at = datetime.now(UTC)
        db.commit()
        db.refresh(round_)
    return round_


def open_rounds_for_student(db: Session, student: Account) -> list[PulseRound]:
    """Open rounds on this student's classes that they have not answered."""
    answered = select(PulseParticipation.round_id).where(
        PulseParticipation.student_id == student.id
    )
    return list(
        db.scalars(
            select(PulseRound)
            .join(TeachingAssignment, TeachingAssignment.id == PulseRound.assignment_id)
            .where(
                PulseRound.closed_at.is_(None),
                TeachingAssignment.class_group_id == student.class_group_id,
                PulseRound.id.not_in(answered),
            )
            .order_by(PulseRound.id)
        ).unique()
    )


def record_reply(
    db: Session,
    round_: PulseRound,
    student: Account,
    *,
    pace: int,
    clarity: int,
    suggestion: str | None,
) -> None:
    """Participation and content written in one transaction and never joined,
    the same split the end-of-term evaluation uses."""
    db.add(PulseParticipation(round_id=round_.id, student_id=student.id))
    db.add(
        PulseReply(
            round_id=round_.id,
            pace=pace,
            clarity=clarity,
            suggestion=(suggestion or "").strip()[:MAX_SUGGESTION_LENGTH] or None,
        )
    )
    db.commit()


def purge_for_term(db: Session, term: AcademicTerm) -> int:
    """Delete every pulse belonging to a term. Returns how many rounds went.

    Called when a term closes. "Formative, not retained" is a promise that has
    to be kept in code, because the moment this data survives into a review
    period it stops being a mid-term check and becomes a second evaluation
    nobody agreed to.
    """
    round_ids = list(
        db.scalars(
            select(PulseRound.id)
            .join(TeachingAssignment, TeachingAssignment.id == PulseRound.assignment_id)
            .where(TeachingAssignment.term_id == term.id)
        )
    )
    if not round_ids:
        return 0

    db.execute(delete(PulseReply).where(PulseReply.round_id.in_(round_ids)))
    db.execute(
        delete(PulseParticipation).where(PulseParticipation.round_id.in_(round_ids))
    )
    db.execute(delete(PulseRound).where(PulseRound.id.in_(round_ids)))
    db.commit()
    return len(round_ids)

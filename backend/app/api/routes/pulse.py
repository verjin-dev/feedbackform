from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import get_current_account, require_faculty, require_student
from app.core.database import get_session
from app.models import Account, PulseRound, Role, TeachingAssignment
from app.services import pulse as pulse_service

router = APIRouter(prefix="/pulse", tags=["pulse"])


class RoundOut(BaseModel):
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
    # False while too few have answered for anything to be shown.
    released: bool
    pace_counts: dict[int, int]
    clarity_mean: float | None
    suggestions: list[str]


class OpenRequest(BaseModel):
    assignment_id: int


class PendingPulse(BaseModel):
    round_id: int
    subject_code: str
    subject_name: str
    faculty_name: str


class ReplyRequest(BaseModel):
    pace: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    suggestion: str | None = Field(default=None, max_length=600)


def _own_assignment(db: Session, faculty: Account, assignment_id: int) -> TeachingAssignment:
    assignment = crud.get_or_404(db, TeachingAssignment, assignment_id)
    if assignment.faculty_id != faculty.id:
        # 404, not 403: confirming it exists tells one instructor about
        # another's teaching.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such subject for you."
        )
    return assignment


def _own_round(db: Session, faculty: Account, round_id: int) -> PulseRound:
    round_ = crud.get_or_404(db, PulseRound, round_id)
    if round_.assignment.faculty_id != faculty.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such check for you."
        )
    return round_


# --- The instructor's side -------------------------------------------------


@router.get("/mine", response_model=list[RoundOut])
def my_rounds(
    faculty: Account = Depends(require_faculty),
    db: Session = Depends(get_session),
):
    """Only ever the caller's own.

    There is deliberately no route for anybody else to read these, including an
    administrator. A mid-term check an instructor asked for stops being useful
    the moment it can be read by the person who reviews them.
    """
    rounds = db.scalars(
        select(PulseRound)
        .join(TeachingAssignment, TeachingAssignment.id == PulseRound.assignment_id)
        .where(TeachingAssignment.faculty_id == faculty.id)
        .order_by(PulseRound.id.desc())
    ).unique()
    return [vars(pulse_service.summarise(db, round_)) for round_ in rounds]


@router.post("/rounds", response_model=RoundOut, status_code=status.HTTP_201_CREATED)
def open_round(
    payload: OpenRequest,
    faculty: Account = Depends(require_faculty),
    db: Session = Depends(get_session),
):
    assignment = _own_assignment(db, faculty, payload.assignment_id)
    round_ = pulse_service.open_round(db, assignment)
    return vars(pulse_service.summarise(db, round_))


@router.post("/rounds/{round_id}/close", response_model=RoundOut)
def close_round(
    round_id: int,
    faculty: Account = Depends(require_faculty),
    db: Session = Depends(get_session),
):
    round_ = pulse_service.close_round(db, _own_round(db, faculty, round_id))
    return vars(pulse_service.summarise(db, round_))


@router.delete("/rounds/{round_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_round(
    round_id: int,
    faculty: Account = Depends(require_faculty),
    db: Session = Depends(get_session),
):
    """Throw it away early.

    The instructor owns this data and can delete it whenever they like, which
    is part of why they can afford to ask an uncomfortable question.
    """
    round_ = _own_round(db, faculty, round_id)
    db.delete(round_)
    db.commit()


# --- The student's side ----------------------------------------------------


@router.get("/pending", response_model=list[PendingPulse])
def pending(
    student: Account = Depends(require_student),
    db: Session = Depends(get_session),
):
    return [
        PendingPulse(
            round_id=round_.id,
            subject_code=round_.assignment.subject.code,
            subject_name=round_.assignment.subject.name,
            faculty_name=round_.assignment.faculty.full_name,
        )
        for round_ in pulse_service.open_rounds_for_student(db, student)
    ]


@router.post("/rounds/{round_id}/reply", status_code=status.HTTP_204_NO_CONTENT)
def reply(
    round_id: int,
    payload: ReplyRequest,
    student: Account = Depends(require_student),
    db: Session = Depends(get_session),
):
    round_ = crud.get_or_404(db, PulseRound, round_id)

    if round_.closed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That check has closed."
        )
    if round_.assignment.class_group_id != student.class_group_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such check for you."
        )

    already = [r.id for r in pulse_service.open_rounds_for_student(db, student)]
    if round_.id not in already:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already answered this one.",
        )

    pulse_service.record_reply(
        db,
        round_,
        student,
        pace=payload.pace,
        clarity=payload.clarity,
        suggestion=payload.suggestion,
    )


# --- What an administrator may see -----------------------------------------


class PulseActivity(BaseModel):
    rounds_open: int
    rounds_total: int
    replies: int


@router.get("/activity", response_model=PulseActivity)
def activity(
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_session),
):
    """Counts only, and only for an administrator.

    That a check ran and how many replied is useful for encouraging the
    practice. What was said is not theirs to read.
    """
    if account.role is not Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    from app.models import PulseReply

    rounds = db.scalars(select(PulseRound)).unique().all()
    return PulseActivity(
        rounds_open=sum(1 for r in rounds if r.is_open),
        rounds_total=len(rounds),
        replies=db.scalar(select(__import__("sqlalchemy").func.count()).select_from(PulseReply)) or 0,
    )

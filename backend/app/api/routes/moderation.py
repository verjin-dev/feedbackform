from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import require_admin
from app.core.database import get_session
from app.models import (
    AcademicTerm,
    Account,
    EvaluationComment,
    EvaluationResponse,
    TeachingAssignment,
)
from app.services import comments as comment_service

router = APIRouter(
    prefix="/comments", tags=["moderation"], dependencies=[Depends(require_admin)]
)


class ModerationRow(BaseModel):
    id: int
    prompt: str
    text: str
    withheld: bool
    withheld_reason: str | None
    subject_code: str
    class_label: str
    faculty_name: str


class WithholdRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


def _rows(db: Session, term: AcademicTerm, withheld: bool | None) -> list[ModerationRow]:
    statement = (
        select(EvaluationComment, TeachingAssignment)
        .join(EvaluationResponse, EvaluationComment.response_id == EvaluationResponse.id)
        .join(TeachingAssignment, TeachingAssignment.id == EvaluationResponse.assignment_id)
        .where(EvaluationResponse.term_id == term.id)
        .order_by(EvaluationComment.id.desc())
    )
    if withheld is not None:
        statement = statement.where(EvaluationComment.withheld.is_(withheld))

    return [
        ModerationRow(
            id=comment.id,
            prompt=comment.prompt.value,
            text=comment.text,
            withheld=comment.withheld,
            withheld_reason=comment.withheld_reason,
            subject_code=assignment.subject.code,
            class_label=assignment.class_group.label,
            faculty_name=assignment.faculty.full_name,
        )
        for comment, assignment in db.execute(statement).all()
    ]


@router.get("", response_model=list[ModerationRow])
def list_comments(
    term_id: int | None = None,
    withheld: bool | None = None,
    db: Session = Depends(get_session),
):
    """Every comment in a term, for moderation.

    Administrators see these before the release rules apply, and before the
    instructor does. That is the point: a comment about somebody's appearance
    or accent should be taken down before the person it targets ever reads it.
    It is also real access to student writing, which is why every withholding
    is recorded against the administrator who did it.
    """
    if term_id is not None:
        term = crud.get_or_404(db, AcademicTerm, term_id)
    else:
        term = db.scalar(select(AcademicTerm).where(AcademicTerm.is_current.is_(True)))
        if term is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No academic term is currently active.",
            )
    return _rows(db, term, withheld)


@router.post("/{comment_id}/withhold", response_model=ModerationRow)
def withhold_comment(
    comment_id: int,
    payload: WithholdRequest,
    db: Session = Depends(get_session),
    actor: Account = Depends(require_admin),
):
    """Hide a comment from the instructor it is about.

    A reason is required. Moderation without one is indistinguishable from
    removing criticism somebody found inconvenient.
    """
    comment = crud.get_or_404(db, EvaluationComment, comment_id)
    comment_service.withhold(db, comment, by=actor, reason=payload.reason)
    return _one(db, comment)


@router.post("/{comment_id}/restore", response_model=ModerationRow)
def restore_comment(
    comment_id: int,
    db: Session = Depends(get_session),
    actor: Account = Depends(require_admin),
):
    comment = crud.get_or_404(db, EvaluationComment, comment_id)
    comment_service.restore(db, comment, by=actor)
    return _one(db, comment)


def _one(db: Session, comment: EvaluationComment) -> ModerationRow:
    response = db.get(EvaluationResponse, comment.response_id)
    assignment = db.get(TeachingAssignment, response.assignment_id)
    return ModerationRow(
        id=comment.id,
        prompt=comment.prompt.value,
        text=comment.text,
        withheld=comment.withheld,
        withheld_reason=comment.withheld_reason,
        subject_code=assignment.subject.code,
        class_label=assignment.class_group.label,
        faculty_name=assignment.faculty.full_name,
    )

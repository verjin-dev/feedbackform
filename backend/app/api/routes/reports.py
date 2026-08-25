from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import require_admin, require_staff
from app.core.database import get_session
from app.models import AcademicTerm, Account, Role
from app.schemas.report import FacultyReport, ResponseRateReport
from app.services.reporting import build_faculty_report, build_response_rate_report

router = APIRouter(prefix="/reports", tags=["reports"])


def _resolve_term(db: Session, term_id: int | None) -> AcademicTerm:
    if term_id is not None:
        return crud.get_or_404(db, AcademicTerm, term_id)

    term = db.scalar(select(AcademicTerm).where(AcademicTerm.is_current.is_(True)))
    if term is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No academic term is currently active.",
        )
    return term


@router.get("/me", response_model=FacultyReport)
def my_report(
    term_id: int | None = None,
    account: Account = Depends(require_staff),
    db: Session = Depends(get_session),
):
    """What a faculty member sees about their own teaching."""
    if account.role is not Role.faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Only faculty accounts have a personal report.",
        )
    return build_faculty_report(db, account, _resolve_term(db, term_id))


@router.get("/faculty/{faculty_id}", response_model=FacultyReport)
def faculty_report(
    faculty_id: int,
    term_id: int | None = None,
    account: Account = Depends(require_staff),
    db: Session = Depends(get_session),
):
    """Admins see anyone; faculty see only themselves.

    In the legacy app this was an unguarded AJAX action taking faculty_id
    straight from the request, so any logged-in session could read any
    instructor's evaluation results.
    """
    if account.role is Role.faculty and account.id != faculty_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own results.",
        )

    faculty = crud.get_or_404(db, Account, faculty_id)
    if faculty.role is not Role.faculty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )

    return build_faculty_report(db, faculty, _resolve_term(db, term_id))


@router.get(
    "/response-rates",
    response_model=ResponseRateReport,
    dependencies=[Depends(require_admin)],
)
def response_rates(
    term_id: int | None = None,
    db: Session = Depends(get_session),
):
    """Participation across the whole term.

    The legacy dashboard counted rows per page with separate queries and had
    no notion of a denominator, so there was no way to tell a well-answered
    questionnaire from a barely answered one.
    """
    return build_response_rate_report(db, _resolve_term(db, term_id))

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import require_admin, require_staff
from app.core.database import get_session
from app.models import AcademicTerm, Account, Role
from app.schemas.report import FacultyReport, ResponseRateReport
from app.services import comments as comment_service
from app.services.reporting import build_faculty_report, build_response_rate_report

router = APIRouter(prefix="/reports", tags=["reports"])


def _attach_comments(db: Session, report: dict, term: AcademicTerm, viewer: Account) -> dict:
    """Written feedback is added last and separately, because who may read it
    is a different question from who may read the numbers."""
    assignments = report["assignments"]
    release = comment_service.comments_for_assignments(
        db,
        term,
        {a["assignment_id"] for a in assignments},
        {a["assignment_id"]: a["responses"] for a in assignments},
        viewer=viewer,
    )
    for assignment in assignments:
        entry = release.get(assignment["assignment_id"])
        assignment["comments"] = entry.comments if entry else []
        assignment["comment_state"] = entry.state if entry else comment_service.RELEASED
        assignment["comment_total"] = entry.total if entry else 0
    return report


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
    term = _resolve_term(db, term_id)
    return _attach_comments(db, build_faculty_report(db, account, term), term, account)


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

    term = _resolve_term(db, term_id)
    return _attach_comments(db, build_faculty_report(db, faculty, term), term, account)


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

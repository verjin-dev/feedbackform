from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import require_admin
from app.core.database import get_session
from app.models import AcademicTerm
from app.services import exporting

router = APIRouter(
    prefix="/exports", tags=["exports"], dependencies=[Depends(require_admin)]
)


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


def _csv(body: str, term: AcademicTerm, kind: str, curriculum: str | None) -> Response:
    name = exporting.file_stem(term, kind, curriculum) + ".csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            # Dated in the filename: an accreditation file is a point-in-time
            # record, and two exports a month apart must not be confusable.
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/curricula", response_model=list[str])
def list_curricula(db: Session = Depends(get_session)):
    """What the exports can be filtered by. Called curriculum rather than
    department because that is what the schema actually holds."""
    return exporting.curricula(db)


@router.get("/summary")
def summary(
    term_id: int | None = None,
    curriculum: str | None = None,
    db: Session = Depends(get_session),
):
    return exporting.summary(db, _resolve_term(db, term_id), curriculum)


@router.get("/questionnaire.csv", response_class=Response)
def questionnaire_csv(term_id: int | None = None, db: Session = Depends(get_session)):
    term = _resolve_term(db, term_id)
    return _csv(exporting.questionnaire_csv(db, term), term, "questionnaire", None)


@router.get("/participation.csv", response_class=Response)
def participation_csv(
    term_id: int | None = None,
    curriculum: str | None = None,
    db: Session = Depends(get_session),
):
    term = _resolve_term(db, term_id)
    body = exporting.participation_csv(db, term, curriculum)
    return _csv(body, term, "participation", curriculum)


@router.get("/results.csv", response_class=Response)
def results_csv(
    term_id: int | None = None,
    curriculum: str | None = Query(None),
    db: Session = Depends(get_session),
):
    term = _resolve_term(db, term_id)
    return _csv(exporting.results_csv(db, term, curriculum), term, "results", curriculum)

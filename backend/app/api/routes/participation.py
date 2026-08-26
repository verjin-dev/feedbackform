from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import require_admin, require_staff
from app.core.config import get_settings
from app.core.database import get_session
from app.models import AcademicTerm
from app.services import notifications, participation

router = APIRouter(prefix="/participation", tags=["participation"])
settings = get_settings()


class OutstandingOut(BaseModel):
    account_id: int
    name: str
    email: str
    class_group_id: int | None
    outstanding: int
    subjects: list[str]
    last_reminded: str | None


class ReminderResult(BaseModel):
    dry_run: bool
    term_id: int
    recipients: int
    # Everyone still outstanding, including those held back by the cooldown, so
    # the number on screen is not mistaken for "everyone who is behind".
    outstanding_total: int
    suppressed_by_cooldown: int
    people: list[OutstandingOut]


class ClassProgressOut(BaseModel):
    class_group_id: int
    label: str
    students: int
    assignments: int
    completed: int
    partial: int
    not_started: int
    completion: float | None


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


def _describe(person: participation.Outstanding) -> dict:
    return {
        "account_id": person.account.id,
        "name": person.account.full_name,
        "email": person.account.email,
        "class_group_id": person.account.class_group_id,
        "outstanding": person.outstanding_count,
        "subjects": person.subjects,
        "last_reminded": person.last_reminded.isoformat() if person.last_reminded else None,
    }


@router.get(
    "/progress",
    response_model=list[ClassProgressOut],
    dependencies=[Depends(require_staff)],
)
def progress(term_id: int | None = None, db: Session = Depends(get_session)):
    """Per class: how many students have finished, started, or not begun.

    Faculty can see this too. Knowing that one of their classes is at 20% while
    another is at 80% is what lets them mention it in the room, which moves the
    number far more than another email does.
    """
    term = _resolve_term(db, term_id)
    return [
        ClassProgressOut(**vars(row) | {"completion": row.completion})
        for row in participation.class_progress(db, term)
    ]


@router.post(
    "/reminders",
    response_model=ReminderResult,
    dependencies=[Depends(require_admin)],
)
def send_reminders(
    background: BackgroundTasks,
    term_id: int | None = None,
    class_group_id: int | None = None,
    dry_run: bool = Query(True, description="Report only. Set false to send."),
    ignore_cooldown: bool = Query(
        False,
        description=(
            "Send even to people reminded recently. For the last day of the "
            "window, not for routine use."
        ),
    ),
    db: Session = Depends(get_session),
):
    """Email students who still have subjects to rate.

    A dry run by default, and the preview lists exactly who would be written to
    and what they still owe. Nobody who has finished is ever included — a
    reminder to someone already done is the fastest way to teach people that
    these messages are not worth opening.
    """
    term = _resolve_term(db, term_id)

    everyone = participation.find_outstanding(
        db, term, class_group_id=class_group_id, ignore_cooldown=True
    )
    eligible = (
        everyone
        if ignore_cooldown
        else participation.find_outstanding(db, term, class_group_id=class_group_id)
    )

    if not dry_run and eligible:
        term_label = f"{term.year} semester {term.semester}"
        for person in eligible:
            background.add_task(
                notifications.send_reminder, person.account, person.subjects, term_label
            )
        participation.record_reminders(db, term, [p.account for p in eligible])

    return ReminderResult(
        dry_run=dry_run,
        term_id=term.id,
        recipients=len(eligible),
        outstanding_total=len(everyone),
        suppressed_by_cooldown=len(everyone) - len(eligible),
        people=[_describe(person) for person in eligible],
    )


@router.get(
    "/qr.svg",
    dependencies=[Depends(require_staff)],
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}}}},
)
def qr_code(scale: int = Query(8, ge=2, le=20), db: Session = Depends(get_session)):
    """A scannable code for the feedback form, as SVG so it prints sharply.

    Meant to go on a slide or a handout: scanning from a seat is a lower bar
    than remembering a URL later, and the gap between those two is most of the
    response rate.
    """
    import segno

    target = f"{settings.app_base_url.rstrip('/')}/evaluate"
    svg = segno.make(target, error="h").svg_inline(scale=scale, dark="#111111")
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )

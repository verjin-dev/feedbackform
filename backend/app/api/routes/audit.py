from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_session
from app.models import AuditEvent

router = APIRouter(
    prefix="/audit", tags=["audit"], dependencies=[Depends(require_admin)]
)


class AuditEventOut(BaseModel):
    id: int
    at: datetime
    actor_email: str
    actor_name: str
    action: str
    entity_type: str
    entity_id: str
    summary: str
    changes: str | None


@router.get("", response_model=list[AuditEventOut])
def list_events(
    entity_type: str | None = None,
    actor_email: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_session),
):
    """Configuration and access changes, newest first.

    Deliberately holds nothing about who submitted an evaluation or what they
    wrote — see the note in app/services/audit.py. This answers "did somebody
    change the questionnaire halfway through?", not "who said that?".
    """
    statement = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if actor_email:
        statement = statement.where(AuditEvent.actor_email == actor_email.lower())
    return db.scalars(statement).all()


@router.get("/entity-types", response_model=list[str])
def entity_types(db: Session = Depends(get_session)):
    return sorted(
        {row for (row,) in db.execute(select(AuditEvent.entity_type).distinct()).all()}
    )

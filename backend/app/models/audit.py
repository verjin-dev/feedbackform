from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditEvent(Base):
    """Who changed what, and when.

    The first question anyone asks when a number looks wrong is "did somebody
    change the questionnaire halfway through?", and until now that was
    unanswerable.

    The actor's name and address are copied in rather than joined. An audit
    trail that loses its subject when the account is deleted answers the
    question least well exactly when it is asked most urgently.
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_at", "at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Nullable, and never the only record of who acted: SET NULL on delete
    # keeps the row while the denormalised fields below keep its meaning.
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("account.id", ondelete="SET NULL")
    )
    actor_email: Mapped[str] = mapped_column(String(255), default="system")
    actor_name: Mapped[str] = mapped_column(String(200), default="System")

    action: Mapped[str] = mapped_column(String(20))  # created | updated | deleted
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(50))

    # Readable without decoding anything: "Academic term 2025-2026 S1".
    summary: Mapped[str] = mapped_column(String(255), default="")

    # "status: open -> closed", one per line. Values that are credentials are
    # never written here, only the fact that they changed.
    changes: Mapped[str | None] = mapped_column(Text)

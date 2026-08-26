from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReminderLog(Base):
    """One row per reminder actually sent.

    Exists so a cooldown can be enforced — a reminder that arrives daily is a
    nag, and people who are nagged unsubscribe rather than respond — and so an
    administrator can see how much prompting a given response rate took.

    Scoped to a term: a reminder sent last semester must not suppress one this
    semester.
    """

    __tablename__ = "reminder_log"
    __table_args__ = (Index("ix_reminder_log_lookup", "term_id", "account_id", "sent_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_term.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

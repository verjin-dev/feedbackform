from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import CommentPrompt


class EvaluationComment(Base):
    """A written answer, hanging off the anonymous response.

    Deliberately attached to EvaluationResponse and not to
    EvaluationSubmission, for the same reason the ratings are: nothing here
    should be traceable to the student who wrote it.

    That said, prose is not anonymous in the way a number is. A student who
    writes "the class after the lab on the 14th" has identified themselves to
    everyone who was in the room, whatever this table stores. The release rules
    in app/services/comments.py exist because the schema alone cannot fix that.
    """

    __tablename__ = "evaluation_comment"
    __table_args__ = (
        UniqueConstraint("response_id", "prompt", name="uq_comment_once_per_prompt"),
        Index("ix_comment_response", "response_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[Uuid] = mapped_column(
        ForeignKey("evaluation_response.id", ondelete="CASCADE")
    )
    prompt: Mapped[CommentPrompt] = mapped_column(
        Enum(CommentPrompt, name="comment_prompt", native_enum=False, length=20)
    )
    text: Mapped[str] = mapped_column(Text)

    # Moderation. A comment about somebody's accent or appearance is not
    # feedback about teaching, and someone has to be able to take it down —
    # with a record of who did and why, so the power is accountable.
    withheld: Mapped[bool] = mapped_column(Boolean, default=False)
    withheld_reason: Mapped[str | None] = mapped_column(String(255))
    withheld_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("account.id", ondelete="SET NULL")
    )
    withheld_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

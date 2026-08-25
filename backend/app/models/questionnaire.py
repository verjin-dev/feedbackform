from sqlalchemy import ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.academic import AcademicTerm
from app.models.base import Base, TimestampMixin


class Criterion(Base, TimestampMixin):
    """Legacy `criteria_list`. Criteria are global; questions are per-term."""

    __tablename__ = "criterion"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

    # Legacy stored ordering in a `text` column and sorted with
    # `order by abs(order_by)` to coerce it back to a number.
    position: Mapped[int] = mapped_column(SmallInteger, default=0)


class Question(Base, TimestampMixin):
    """Legacy `question_list`."""

    __tablename__ = "question"
    __table_args__ = (
        Index("ix_question_term_criterion", "term_id", "criterion_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_term.id", ondelete="CASCADE")
    )
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("criterion.id", ondelete="RESTRICT")
    )
    text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger, default=0)

    term: Mapped[AcademicTerm] = relationship()
    criterion: Mapped[Criterion] = relationship(lazy="joined")

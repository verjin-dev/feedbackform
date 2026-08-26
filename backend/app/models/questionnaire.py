from sqlalchemy import ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.academic import AcademicTerm
from app.models.base import Base, TimestampMixin


class Criterion(Base, TimestampMixin):
    """Legacy `criteria_list`. Criteria are global; questions are per-term."""

    __tablename__ = "criterion"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

    # Tamil, where somebody at the college has supplied it. English is the
    # fallback and never the empty string: a criterion heading that vanishes
    # for Tamil readers is worse than one they read in English.
    name_ta: Mapped[str | None] = mapped_column(String(255))

    # Legacy stored ordering in a `text` column and sorted with
    # `order by abs(order_by)` to coerce it back to a number.
    position: Mapped[int] = mapped_column(SmallInteger, default=0)

    def display_name(self, language: str) -> str:
        return (self.name_ta or self.name) if language == "ta" else self.name


class Question(Base, TimestampMixin):
    """Legacy `question_list`."""

    __tablename__ = "question"
    __table_args__ = (
        Index("ix_question_term_criterion", "term_id", "criterion_id", "position"),
        # The student-facing lookup: the questions this term asks of this
        # department.
        Index("ix_question_term_scope", "term_id", "curriculum"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_term.id", ondelete="CASCADE")
    )
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("criterion.id", ondelete="RESTRICT")
    )
    text: Mapped[str] = mapped_column(Text)

    # The wording is the college's, not the interface's, so it cannot be
    # shipped in a translation file -- it has to be entered per question, and
    # until it is, English stands in. A half-translated questionnaire is
    # readable; one where untranslated questions disappear is not.
    text_ta: Mapped[str | None] = mapped_column(Text)

    position: Mapped[int] = mapped_column(SmallInteger, default=0)

    # NULL means every department answers it. A value means only students whose
    # class carries that curriculum are asked.
    #
    # There is no department entity in this schema; curriculum on the class
    # group is the closest thing to one, and the reports already filter on it,
    # so departments are spelled the same way here rather than introducing a
    # second, competing notion of what a department is. Stored as entered and
    # compared case-insensitively after stripping, because the legacy data has
    # both "B.E. IT" and "B.E IT ".
    curriculum: Mapped[str | None] = mapped_column(String(100))

    @property
    def is_core(self) -> bool:
        return self.curriculum is None

    def display_text(self, language: str) -> str:
        return (self.text_ta or self.text) if language == "ta" else self.text

    term: Mapped[AcademicTerm] = relationship()
    criterion: Mapped[Criterion] = relationship(lazy="joined")

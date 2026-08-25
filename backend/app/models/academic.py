from sqlalchemy import Enum, Index, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import TermStatus


class AcademicTerm(Base, TimestampMixin):
    """Legacy `academic_list`.

    `is_current` replaces `is_default`. The legacy app cleared the previous
    default in a separate statement with nothing enforcing that exactly one row
    won; the partial unique index below makes two current terms impossible.
    """

    __tablename__ = "academic_term"
    __table_args__ = (
        UniqueConstraint("year", "semester", name="uq_academic_term_year_semester"),
        Index(
            "uq_academic_term_single_current",
            "is_current",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[str] = mapped_column(String(20))
    semester: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[TermStatus] = mapped_column(
        Enum(TermStatus, name="term_status", native_enum=False, length=20),
        default=TermStatus.pending,
    )
    is_current: Mapped[bool] = mapped_column(default=False)

    @property
    def is_accepting_submissions(self) -> bool:
        return self.status is TermStatus.open

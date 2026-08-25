from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ClassGroup(Base, TimestampMixin):
    """Legacy `class_list`. Renamed because "class" is a reserved word in most
    of the languages this now passes through."""

    __tablename__ = "class_group"
    __table_args__ = (
        UniqueConstraint("curriculum", "level", "section", name="uq_class_group_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    curriculum: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(50))
    section: Mapped[str] = mapped_column(String(50))

    @property
    def label(self) -> str:
        return f"{self.curriculum} {self.level}-{self.section}"


class Subject(Base, TimestampMixin):
    """Legacy `subject_list`."""

    __tablename__ = "subject"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

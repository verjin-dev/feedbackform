from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.academic import AcademicTerm
from app.models.account import Account
from app.models.base import Base, TimestampMixin
from app.models.catalog import ClassGroup, Subject


class TeachingAssignment(Base, TimestampMixin):
    """Legacy `restriction_list`.

    Renamed because it never restricted anything — it is the
    faculty x class x subject tuple for a term, and it is the join every screen
    in the application hangs off. The old name misled every file that used it.
    """

    __tablename__ = "teaching_assignment"
    __table_args__ = (
        UniqueConstraint(
            "term_id",
            "faculty_id",
            "class_group_id",
            "subject_id",
            name="uq_teaching_assignment_identity",
        ),
        # The student-facing lookup: which assignments exist for my class this
        # term. Unindexed in the legacy schema.
        Index("ix_teaching_assignment_lookup", "term_id", "class_group_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_term.id", ondelete="CASCADE")
    )
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT")
    )
    class_group_id: Mapped[int] = mapped_column(
        ForeignKey("class_group.id", ondelete="RESTRICT")
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subject.id", ondelete="RESTRICT")
    )

    term: Mapped[AcademicTerm] = relationship()
    faculty: Mapped[Account] = relationship(lazy="joined")
    class_group: Mapped[ClassGroup] = relationship(lazy="joined")
    subject: Mapped[Subject] = relationship(lazy="joined")

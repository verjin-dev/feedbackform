import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.identifiers import uuid7
from app.models.academic import AcademicTerm
from app.models.account import Account
from app.models.assignment import TeachingAssignment
from app.models.base import Base
from app.models.questionnaire import Question

# ---------------------------------------------------------------------------
# The anonymity split.
#
# The legacy schema stored student_id in the same row as faculty_id and the
# answers, so any rating could be attributed to the student who gave it. These
# three tables replace that with two disconnected halves:
#
#   EvaluationSubmission  — records THAT a student completed an assignment.
#                           Carries no answers. Drives duplicate prevention
#                           and response-rate reporting.
#   EvaluationResponse    — an anonymous answer set for an assignment.
#                           Carries no student reference.
#   EvaluationRating      — the individual answers, hanging off a Response.
#
# Both halves are written in one transaction, and nothing joins them:
#
#   1. Response has no student column and no foreign key to Submission.
#   2. Response has no timestamp column.
#   3. Reports aggregate; no endpoint returns an individual Response.
#
# KNOWN LIMITATION — response ids are UUIDv7, which is time-ordered.
#
# A v7 id encodes its creation time to the millisecond in the high 48 bits, so
# points 1 and 2 above do not deliver anonymity against anyone holding the ids
# or direct database access. Two attacks remain open:
#
#   - Read the timestamp out of a response id and match it against
#     evaluation_submission.submitted_at.
#   - Sort responses by id and zip them against submissions ordered by their
#     sequential primary key.
#
# This was chosen deliberately for index locality on insert. It means the
# anonymity guarantee currently holds only at the API surface, and not against
# the database itself — so database access must be treated as sensitive rather
# than routine, and no response id should ever be exposed to a client.
#
# To close it later, the smallest change is uuid4 here plus a non-sequential
# key on evaluation_submission; coarsening submitted_at alone is not enough,
# because id ordering re-links the rows on its own.
# ---------------------------------------------------------------------------


class EvaluationSubmission(Base):
    """Proof of participation. Deliberately holds no opinions."""

    __tablename__ = "evaluation_submission"
    __table_args__ = (
        # This is what actually prevents a second submission. The legacy app
        # relied on the UI hiding assignments the student had already rated,
        # which a repeated POST bypassed.
        UniqueConstraint(
            "term_id", "student_id", "assignment_id", name="uq_evaluation_submission_once"
        ),
        Index("ix_evaluation_submission_rate", "term_id", "assignment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_term.id", ondelete="CASCADE")
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_assignment.id", ondelete="CASCADE")
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    term: Mapped[AcademicTerm] = relationship()
    student: Mapped[Account] = relationship()
    assignment: Mapped[TeachingAssignment] = relationship()


class EvaluationResponse(Base):
    """An anonymous answer set. See the note above, including the UUIDv7
    limitation, before adding columns or exposing ids."""

    __tablename__ = "evaluation_response"
    __table_args__ = (Index("ix_evaluation_response_report", "term_id", "assignment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    term_id: Mapped[int] = mapped_column(
        ForeignKey("academic_term.id", ondelete="CASCADE")
    )
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_assignment.id", ondelete="CASCADE")
    )

    assignment: Mapped[TeachingAssignment] = relationship()
    ratings: Mapped[list["EvaluationRating"]] = relationship(
        back_populates="response", cascade="all, delete-orphan"
    )


class EvaluationRating(Base):
    """Legacy `evaluation_answers`, which had no primary key at all."""

    __tablename__ = "evaluation_rating"
    __table_args__ = (
        UniqueConstraint("response_id", "question_id", name="uq_evaluation_rating_once"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_in_range"),
        Index("ix_evaluation_rating_question", "question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    response_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_response.id", ondelete="CASCADE")
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id", ondelete="RESTRICT")
    )
    rating: Mapped[int] = mapped_column(SmallInteger)

    response: Mapped[EvaluationResponse] = relationship(back_populates="ratings")
    question: Mapped[Question] = relationship()

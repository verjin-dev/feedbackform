from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.assignment import TeachingAssignment
from app.models.base import Base

# --------------------------------------------------------------------------
# The mid-term check.
#
# End-of-term feedback reaches an instructor after the students who gave it
# have left the course. It can improve next year for somebody else. A mid-term
# check is the only version that can help the people who filled it in, which is
# also the only version students have a selfish reason to complete.
#
# It is deliberately NOT the same thing as an evaluation, and the separation is
# load-bearing:
#
#   - It never enters a report, an export, a cohort band or a trend. Nothing
#     here is evidence about an instructor; it is a note to themselves.
#   - Only the instructor sees it. An administrator can see that a round ran
#     and how many replied, never what was said.
#   - It is deleted when the term closes. "Formative, not retained" is a
#     promise that has to be kept in code or it is not a promise.
#
# Take any of those away and an instructor has a reason not to ask honestly,
# which makes the whole thing worthless.
# --------------------------------------------------------------------------


class PulseRound(Base):
    """One mid-term check, opened by an instructor on their own subject."""

    __tablename__ = "pulse_round"
    __table_args__ = (Index("ix_pulse_round_assignment", "assignment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("teaching_assignment.id", ondelete="CASCADE")
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignment: Mapped[TeachingAssignment] = relationship(lazy="joined")

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class PulseParticipation(Base):
    """That a student answered. Holds no answers, like its evaluation
    counterpart, and exists to stop a second reply and to give a rate."""

    __tablename__ = "pulse_participation"
    __table_args__ = (
        UniqueConstraint("round_id", "student_id", name="uq_pulse_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(
        ForeignKey("pulse_round.id", ondelete="CASCADE")
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))


class PulseReply(Base):
    """What was said. No link to the student, by the same split the evaluation
    responses use."""

    __tablename__ = "pulse_reply"
    __table_args__ = (Index("ix_pulse_reply_round", "round_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(
        ForeignKey("pulse_round.id", ondelete="CASCADE")
    )
    # 1 = much too slow, 3 = about right, 5 = much too fast. Not a quality
    # score: there is no good end of this scale, which is the point.
    pace: Mapped[int] = mapped_column(SmallInteger)
    # 1-5, higher is better.
    clarity: Mapped[int] = mapped_column(SmallInteger)
    suggestion: Mapped[str | None] = mapped_column(Text)

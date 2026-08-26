from app.models.academic import AcademicTerm
from app.models.account import Account
from app.models.assignment import TeachingAssignment
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.catalog import ClassGroup, Subject
from app.models.comment import EvaluationComment
from app.models.enums import CommentPrompt, Role, TermStatus
from app.models.evaluation import (
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
)
from app.models.pulse import PulseParticipation, PulseReply, PulseRound
from app.models.questionnaire import Criterion, Question
from app.models.reminder import ReminderLog

__all__ = [
    "AcademicTerm",
    "Account",
    "AuditEvent",
    "Base",
    "ClassGroup",
    "CommentPrompt",
    "Criterion",
    "EvaluationComment",
    "EvaluationRating",
    "EvaluationResponse",
    "EvaluationSubmission",
    "PulseParticipation",
    "PulseReply",
    "PulseRound",
    "Question",
    "ReminderLog",
    "Role",
    "Subject",
    "TeachingAssignment",
    "TermStatus",
]

# Attaching the audit listener here means it is installed by importing the
# models, so no code path can write to the database without it.
from app.services.audit import install as _install_audit  # noqa: E402

_install_audit()

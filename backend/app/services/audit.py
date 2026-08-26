"""Recording who changed what.

Attached to the session rather than sprinkled through the routes: a log that
depends on every future author remembering to call it is a log with holes in
exactly the places somebody wanted them.

WHAT IS DELIBERATELY NOT AUDITED

The anonymity design says no rating, comment or pulse reply can be traced to
the student who gave it. An audit trail recording "student 41 submitted at
14:02" would be a back door around that, readable by every administrator, and
would undo work done across three phases. So:

  - Evaluation submissions, responses, ratings and comment *content* are never
    written here.
  - Nothing about the mid-term pulse is written here at all. It is not retained
    past the term, and an audit row would outlive the thing it describes.

What is audited is configuration and access: the questionnaire, the assignment
matrix, terms and their windows, accounts, and moderation decisions. Those are
the changes that alter what the system measures or who may see it, and they are
the ones somebody may later need to account for.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent

ACTOR_KEY = "audit_actor"


def set_actor(session: Session, account: Any | None) -> None:
    """Recorded on the session rather than in a ContextVar.

    FastAPI runs sync dependencies in a threadpool, and a ContextVar set there
    is set on that worker's copy of the context — the endpoint then runs with
    its own copy and never sees it, so every change was attributed to "system".
    The session is the object the listener already holds and is scoped to
    exactly one unit of work, which is what this needs.
    """
    if account is None:
        session.info.pop(ACTOR_KEY, None)
    else:
        session.info[ACTOR_KEY] = (account.id, account.email, account.full_name)


def current_actor(session: Session) -> tuple[int | None, str, str]:
    return session.info.get(ACTOR_KEY) or (None, "system", "System")


# Only these are recorded. An allowlist rather than a denylist, so a model
# added later is silent until somebody decides it should not be.
AUDITED = {
    "AcademicTerm",
    "Account",
    "ClassGroup",
    "Criterion",
    "EvaluationComment",
    "Question",
    "Subject",
    "TeachingAssignment",
}

# Never written for any model. Only that a credential changed is recorded.
REDACTED_ALWAYS = {"password_hash", "legacy_md5"}

# Redacted per model, because the same column name means different things.
#
# A question's wording is auditable content — "did somebody reword the
# questionnaire halfway through?" is the question this log exists to answer, so
# redacting Question.text would make it useless for its main purpose. A
# comment's text is a student writing in confidence and is never repeated here.
REDACTED_BY_MODEL = {
    "EvaluationComment": {"text", "withheld_reason"},
}


def _is_redacted(model: str, field: str) -> bool:
    return field in REDACTED_ALWAYS or field in REDACTED_BY_MODEL.get(model, set())

# Noise. Every row has these and they say nothing about intent.
IGNORED_FIELDS = {"created_at", "updated_at"}


def _describe(instance: Any) -> str:
    """A line somebody can read without looking anything up.

    Handled per model rather than by hunting for a likely-looking attribute: a
    generic search found `text` on EvaluationComment and put a student's own
    words in the summary, which is exactly what this log must not carry.
    """
    name = type(instance).__name__

    if name == "AcademicTerm":
        return f"Academic term {instance.year} S{instance.semester}"
    if name == "EvaluationComment":
        # The decision is auditable. What was written is not repeated here.
        return f"Written feedback #{instance.id}"
    if name == "TeachingAssignment":
        return f"Assignment #{instance.id}"
    if name == "Question":
        return f"Question: {(instance.text or '').strip()[:80]}"

    for attribute in ("label", "full_name", "code", "name"):
        value = getattr(instance, attribute, None)
        if isinstance(value, str) and value.strip():
            return f"{name}: {value.strip()[:80]}"

    return f"{name} #{getattr(instance, 'id', '?')}"


def _changed_fields(instance: Any) -> str | None:
    state = inspect(instance)
    model = type(instance).__name__
    lines: list[str] = []

    for attribute in state.mapper.column_attrs:
        field = attribute.key
        if field in IGNORED_FIELDS:
            continue

        history = state.attrs[field].history
        if not history.has_changes():
            continue

        if _is_redacted(model, field):
            # That it changed is the auditable fact; what it changed to is not.
            lines.append(f"{field}: changed")
            continue

        before = history.deleted[0] if history.deleted else None
        after = history.added[0] if history.added else None
        lines.append(f"{field}: {before!r} -> {after!r}")

    return "\n".join(lines) if lines else None


def _event_for(session: Session, instance: Any, action: str) -> AuditEvent | None:
    if type(instance).__name__ not in AUDITED:
        return None

    changes = _changed_fields(instance) if action == "updated" else None
    if action == "updated" and changes is None:
        # A flush that touched nothing is not a change worth a row.
        return None

    actor_id, actor_email, actor_name = current_actor(session)
    return AuditEvent(
        actor_id=actor_id,
        actor_email=actor_email,
        actor_name=actor_name,
        action=action,
        entity_type=type(instance).__name__,
        entity_id=str(getattr(instance, "id", "")),
        summary=_describe(instance)[:255],
        changes=changes,
    )


def install() -> None:
    """Attach the listener. Called once, from app.models."""

    @event.listens_for(Session, "before_flush")
    def _record(session: Session, _flush_context, _instances) -> None:
        pending: list[AuditEvent] = []

        for instance in session.new:
            entry = _event_for(session, instance, "created")
            if entry is not None:
                pending.append(entry)

        for instance in session.dirty:
            if not session.is_modified(instance, include_collections=False):
                continue
            entry = _event_for(session, instance, "updated")
            if entry is not None:
                pending.append(entry)

        for instance in session.deleted:
            entry = _event_for(session, instance, "deleted")
            if entry is not None:
                pending.append(entry)

        # AuditEvent is not in AUDITED, so adding these cannot cascade.
        for entry in pending:
            session.add(entry)

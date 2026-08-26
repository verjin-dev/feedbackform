"""When written feedback may be read, and by whom.

Ratings are anonymous because the schema was rebuilt to make them so. Prose is
not anonymous in the same way, and no schema fixes that: a student who writes
"the class after the lab on the 14th" has identified themselves to everyone who
was in the room.

So the protection is procedural, and all of it lives here:

  1. A release threshold. Below a handful of responses, authorship is often
     obvious from content alone, so nothing is shown at all.
  2. Release only once the evaluation window has closed. An instructor reading
     criticism while still holding the marking pen is a conflict the system
     should not create.
  3. Withheld comments never reach the person they are about, and withholding
     is recorded against the administrator who did it.

The fourth safeguard is not code: the student is told these rules above the box
before they type. That lives in the evaluate screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    CommentPrompt,
    EvaluationComment,
    EvaluationResponse,
    Role,
    TermStatus,
)

# Below this many responses for an assignment, no comment on it is shown to
# anyone but an administrator. With three, who wrote what is frequently
# guessable from the content.
MIN_RESPONSES_FOR_COMMENTS = 5

MAX_COMMENT_LENGTH = 1500

PROMPT_TEXT = {
    CommentPrompt.helped: "What helped you learn in this subject?",
    CommentPrompt.change: "What would you change?",
}

# Why a set of comments is not being shown, in words that can go on screen.
WITHHELD_TOO_FEW = "too_few_responses"
WITHHELD_WINDOW_OPEN = "window_open"
RELEASED = "released"


@dataclass
class CommentRelease:
    state: str
    comments: list[dict]
    total: int  # including any withheld or suppressed, for an administrator

    @property
    def released(self) -> bool:
        return self.state == RELEASED


def release_state(
    term: AcademicTerm, response_count: int, *, viewer: Account
) -> str:
    """Administrators can always read comments, because someone has to be able
    to act on an abusive one before the person it targets ever sees it. That is
    a real exception and not an oversight: the moderation queue cannot be
    gated behind the same rules as the results."""
    if viewer.role is Role.admin:
        return RELEASED
    if term.status is not TermStatus.closed:
        return WITHHELD_WINDOW_OPEN
    if response_count < MIN_RESPONSES_FOR_COMMENTS:
        return WITHHELD_TOO_FEW
    return RELEASED


def comments_for_assignments(
    db: Session,
    term: AcademicTerm,
    assignment_ids: set[int],
    response_counts: dict[int, int],
    *,
    viewer: Account,
) -> dict[int, CommentRelease]:
    """assignment id -> what this viewer may see of its comments."""
    if not assignment_ids:
        return {}

    rows = db.execute(
        select(
            EvaluationResponse.assignment_id,
            EvaluationComment.id,
            EvaluationComment.prompt,
            EvaluationComment.text,
            EvaluationComment.withheld,
            EvaluationComment.withheld_reason,
        )
        .join(EvaluationComment, EvaluationComment.response_id == EvaluationResponse.id)
        .where(EvaluationResponse.assignment_id.in_(assignment_ids))
        .order_by(EvaluationComment.id)
    ).all()

    grouped: dict[int, list[dict]] = {}
    for assignment_id, comment_id, prompt, text, withheld, reason in rows:
        grouped.setdefault(assignment_id, []).append(
            {
                "id": comment_id,
                "prompt": prompt.value if hasattr(prompt, "value") else str(prompt),
                "text": text,
                "withheld": bool(withheld),
                "withheld_reason": reason,
            }
        )

    is_admin = viewer.role is Role.admin
    result: dict[int, CommentRelease] = {}
    for assignment_id in assignment_ids:
        all_comments = grouped.get(assignment_id, [])
        state = release_state(
            term, response_counts.get(assignment_id, 0), viewer=viewer
        )

        if state != RELEASED:
            visible: list[dict] = []
        elif is_admin:
            # An administrator sees withheld comments too — that is the queue.
            visible = all_comments
        else:
            visible = [c for c in all_comments if not c["withheld"]]
            for comment in visible:
                comment.pop("withheld_reason", None)

        result[assignment_id] = CommentRelease(
            state=state, comments=visible, total=len(all_comments)
        )
    return result


def save_comments(
    db: Session,
    response: EvaluationResponse,
    entries: list[tuple[CommentPrompt, str]],
) -> int:
    """Written alongside the ratings, in the same transaction.

    Blank answers are dropped rather than stored: an empty row is not an
    opinion, and counting it as one would make participation look better than
    it is.
    """
    written = 0
    for prompt, text in entries:
        cleaned = text.strip()
        if not cleaned:
            continue
        db.add(
            EvaluationComment(
                response_id=response.id, prompt=prompt, text=cleaned[:MAX_COMMENT_LENGTH]
            )
        )
        written += 1
    return written


def withhold(
    db: Session, comment: EvaluationComment, *, by: Account, reason: str
) -> EvaluationComment:
    comment.withheld = True
    comment.withheld_reason = reason.strip()[:255]
    comment.withheld_by_id = by.id
    comment.withheld_at = datetime.now(UTC)
    db.commit()
    db.refresh(comment)
    return comment


def restore(db: Session, comment: EvaluationComment, *, by: Account) -> EvaluationComment:
    """Reversible on purpose. Moderation that cannot be undone invites either
    over-caution or nobody using it at all."""
    comment.withheld = False
    comment.withheld_reason = None
    comment.withheld_by_id = by.id
    comment.withheld_at = datetime.now(UTC)
    db.commit()
    db.refresh(comment)
    return comment

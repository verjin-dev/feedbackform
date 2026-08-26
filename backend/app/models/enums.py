import enum


class Role(str, enum.Enum):
    """Replaces the legacy integer login type (1/2/3) and, with it, the trick
    of using a client-supplied index to pick which table to authenticate
    against."""

    admin = "admin"
    faculty = "faculty"
    student = "student"


class TermStatus(str, enum.Enum):
    """Replaces `status int(1)` documented only in a column comment as
    '0=Pending,1=Start,2=Closed'."""

    pending = "pending"
    open = "open"
    closed = "closed"


class CommentPrompt(str, enum.Enum):
    """The two open questions.

    Fixed rather than configurable. Free-text prompts are easy to word badly —
    "any other comments?" invites the least useful answers there are — and
    these two are the pair that consistently produce something an instructor
    can act on.
    """

    helped = "helped"  # What helped you learn?
    change = "change"  # What would you change?

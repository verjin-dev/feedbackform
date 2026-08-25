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

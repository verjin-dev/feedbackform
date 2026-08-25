import secrets
import time
import uuid

# Python's stdlib gains uuid.uuid7() in 3.14; this targets 3.12, so the
# RFC 9562 layout is built here rather than taking a dependency for 15 lines.
#
#   bits 127..80  48-bit Unix timestamp in milliseconds
#   bits  79..76  version (0111)
#   bits  75..64  12 bits of randomness
#   bits  63..62  variant (10)
#   bits  61..0   62 bits of randomness

_VERSION = 0x7
_VARIANT = 0b10


def uuid7() -> uuid.UUID:
    """A time-ordered UUID.

    Sorts by creation time, which gives good B-tree index locality on inserts
    compared with uuid4's random distribution.

    Be aware of what that ordering means where these are used on
    EvaluationResponse: a v7 id discloses when it was created, to the
    millisecond. See the note in app/models/evaluation.py.
    """
    timestamp_ms = int(time.time() * 1000) & 0xFFFF_FFFF_FFFF

    value = timestamp_ms << 80
    value |= _VERSION << 76
    value |= secrets.randbits(12) << 64
    value |= _VARIANT << 62
    value |= secrets.randbits(62)

    return uuid.UUID(int=value)


def uuid7_timestamp_ms(value: uuid.UUID) -> int:
    """Recover the embedded creation time. Exists mostly to make it obvious in
    review that this information is recoverable by anyone holding the id."""
    return value.int >> 80

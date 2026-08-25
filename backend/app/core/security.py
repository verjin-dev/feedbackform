import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from app.core.config import get_settings
from app.models.enums import Role

settings = get_settings()

# argon2-cffi defaults to Argon2id with parameters the maintainers keep current
# with the RFC 9106 guidance. Pinning our own numbers here would freeze them.
_hasher = PasswordHasher()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than we now use."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def verify_legacy_md5(stored_md5: str, password: str) -> bool:
    """Check a password against a hash carried over from the PHP application.

    Unsalted MD5 is not a password hash and this function does not pretend
    otherwise. It exists solely so migrated accounts can log in once, at which
    point the caller rehashes with Argon2id and clears the legacy column.
    """
    computed = hashlib.md5(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(computed, stored_md5.strip().lower())


def create_access_token(account_id: int, role: Role) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(account_id),
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Returns the claims, or None for anything not valid and unexpired.

    Callers get no detail about why a token failed; that distinction is only
    useful to someone probing it.
    """
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

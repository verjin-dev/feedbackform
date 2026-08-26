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


# --- Links sent by email ---------------------------------------------------

RESET_PURPOSE = "password-reset"
INVITE_PURPOSE = "invitation"


def credential_fingerprint(password_hash: str | None, legacy_md5: str | None) -> str:
    """A short digest of whatever credential the account currently holds.

    Carried in reset and invitation links and re-checked when one is redeemed.
    Setting a password changes the credential, so the fingerprint stops
    matching and every outstanding link for that account dies — which makes
    them single-use, and revokes them on any password change, without a table
    to store or expire.
    """
    material = password_hash or legacy_md5 or ""
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def create_link_token(
    account_id: int, purpose: str, fingerprint: str, ttl_seconds: int
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(account_id),
            "purpose": purpose,
            "fp": fingerprint,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_link_token(token: str, purpose: str) -> dict[str, Any] | None:
    """Claims, or None. A token minted for one purpose is not valid for
    another, so an invitation cannot be replayed as a session."""
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if claims.get("purpose") != purpose:
        return None
    return claims

"""The messages the system sends, and the links inside them."""

from __future__ import annotations

from urllib.parse import urlencode

from app.core.config import get_settings
from app.core.email import Message, send
from app.core.security import (
    INVITE_PURPOSE,
    RESET_PURPOSE,
    create_link_token,
    credential_fingerprint,
)
from app.models import Account

settings = get_settings()


def _link(path: str, token: str) -> str:
    base = settings.app_base_url.rstrip("/")
    return f"{base}{path}?{urlencode({'token': token})}"


def password_reset_token(account: Account) -> str:
    return create_link_token(
        account.id,
        RESET_PURPOSE,
        credential_fingerprint(account.password_hash, account.legacy_md5),
        settings.password_reset_ttl_minutes * 60,
    )


def invitation_token(account: Account) -> str:
    return create_link_token(
        account.id,
        INVITE_PURPOSE,
        credential_fingerprint(account.password_hash, account.legacy_md5),
        settings.invitation_ttl_hours * 3600,
    )


def send_password_reset(account: Account) -> str:
    """Returns the token so callers can log or test it. The link itself only
    ever travels by email."""
    token = password_reset_token(account)
    hours_or_minutes = settings.password_reset_ttl_minutes

    send(
        Message(
            to=account.email,
            subject="Reset your Faculty Evaluation password",
            body=(
                f"Hello {account.first_name},\n\n"
                "Someone asked to reset the password for this address. Open the "
                "link below to choose a new one:\n\n"
                f"{_link('/reset-password', token)}\n\n"
                f"The link works for {hours_or_minutes} minutes and can only be "
                "used once.\n\n"
                "If this wasn't you, nothing has changed and you can ignore this "
                "message. Your current password still works.\n"
            ),
        )
    )
    return token


def send_invitation(account: Account, *, invited_by: str | None = None) -> str:
    token = invitation_token(account)
    days = settings.invitation_ttl_hours // 24
    who = f" by {invited_by}" if invited_by else ""

    send(
        Message(
            to=account.email,
            subject="Your Faculty Evaluation account",
            body=(
                f"Hello {account.first_name},\n\n"
                f"An account has been created for you{who} on the Faculty "
                "Evaluation system. Choose a password to get started:\n\n"
                f"{_link('/set-password', token)}\n\n"
                f"The link works for {days} days. If it expires, ask your "
                "administrator to send another.\n\n"
                "You will use this account to give feedback on your subjects at "
                "the end of term. Your answers are recorded without your name.\n"
            ),
        )
    )
    return token


def send_reminder(account: Account, subjects: list[str], term_label: str) -> None:
    """Names the subjects actually outstanding.

    A generic "please complete your feedback" makes the recipient go and find
    out what is left; listing it means the decision to respond and the
    information needed to act on it arrive together.
    """
    listed = "\n".join(f"  - {subject}" for subject in subjects)
    count = len(subjects)
    plural = "s" if count != 1 else ""
    evaluate_url = f"{settings.app_base_url.rstrip('/')}/evaluate"

    send(
        Message(
            to=account.email,
            subject=f"{count} subject{plural} still to review — {term_label}",
            body=(
                f"Hello {account.first_name},\n\n"
                f"You have {count} subject{plural} left to give feedback on for "
                f"{term_label}:\n\n"
                f"{listed}\n\n"
                "It takes about a minute and a half each:\n\n"
                f"{evaluate_url}\n\n"
                "Your answers are recorded without your name. Your instructors "
                "see only the combined results for the whole class, and they see "
                "them after marks are in.\n"
            ),
        )
    )

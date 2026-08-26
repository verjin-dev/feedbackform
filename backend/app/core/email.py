"""Outbound email.

The application had none at all, which is why migrated accounts were given a
rehash-on-login path rather than a forced reset: there was no way to tell
anyone. Everything that follows — password resets, invitations, the response
rate reminders — needs this first.

Three backends. The default is "console", deliberately: a deployment that has
not been configured should print its mail to the log rather than silently fail,
and it must never mail real students because someone forgot to set a host.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Message:
    to: str
    subject: str
    body: str

    def as_email(self, sender: str, reply_to: str | None) -> EmailMessage:
        message = EmailMessage()
        message["From"] = sender
        message["To"] = self.to
        message["Subject"] = self.subject
        if reply_to:
            message["Reply-To"] = reply_to
        message.set_content(self.body)
        return message


class Mailer:
    def send(self, message: Message) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleMailer(Mailer):
    """Prints instead of sending. What a developer sees, and what an
    unconfigured production deployment does rather than doing harm."""

    def send(self, message: Message) -> None:
        logger.info(
            "EMAIL (not sent — console backend)\n  To: %s\n  Subject: %s\n\n%s",
            message.to,
            message.subject,
            message.body,
        )


@dataclass
class MemoryMailer(Mailer):
    """Captures messages so tests can read them."""

    outbox: list[Message] = field(default_factory=list)

    def send(self, message: Message) -> None:
        self.outbox.append(message)


class SmtpMailer(Mailer):
    def send(self, message: Message) -> None:
        settings = get_settings()
        email = message.as_email(settings.email_from, settings.email_reply_to)

        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
        ) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password or "")
            server.send_message(email)


_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        backend = get_settings().email_backend
        _mailer = {
            "console": ConsoleMailer,
            "memory": MemoryMailer,
            "smtp": SmtpMailer,
        }[backend]()
    return _mailer


def set_mailer(mailer: Mailer | None) -> None:
    """Test seam. Passing None restores the configured backend."""
    global _mailer
    _mailer = mailer


def send(message: Message) -> None:
    """Never raises into the request.

    A reset request that returns 500 because the mail server is briefly down
    tells the caller their address exists, and leaves the user with an error
    they cannot act on. Delivery problems belong in the log.
    """
    try:
        get_mailer().send(message)
    except Exception:  # noqa: BLE001 - any delivery failure is the same to us
        logger.exception("Failed to send mail to %s", message.to)

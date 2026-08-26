from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.account import Account
from app.models.base import Base, TimestampMixin


class ExternalIdentity(Base, TimestampMixin):
    """A college directory account linked to an account here.

    Keyed on the provider's subject identifier, never on the email address.
    An address gets reassigned when somebody leaves and their successor is
    given the same one -- link on the address and that successor signs in as
    their predecessor, inheriting whatever that account could see. The subject
    is stable for the life of the directory account and is not reused.

    The address is stored anyway, but only as a record of what it was when the
    link was made: it is what an administrator reads on the accounts screen,
    and it is what makes a stale link recognisable.
    """

    __tablename__ = "external_identity"
    __table_args__ = (
        # One directory account maps to at most one account here. Without this,
        # two rows could point one directory identity at two accounts and which
        # one you got would depend on row order.
        UniqueConstraint("provider", "subject", name="uq_external_identity_subject"),
        # And one account holds at most one identity per provider, so "unlink"
        # is unambiguous.
        UniqueConstraint("provider", "account_id", name="uq_external_identity_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # The issuer, as the provider states it. Recorded rather than a fixed
    # string, so a tenant migration is visible instead of silently matching.
    provider: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))

    account_id: Mapped[int] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), index=True
    )

    # What the directory said the address was when the link was made. Not used
    # for matching on later sign-ins -- the subject is.
    email_at_link: Mapped[str] = mapped_column(String(255))

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account: Mapped[Account] = relationship()

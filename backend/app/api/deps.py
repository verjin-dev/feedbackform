from collections.abc import Callable, Iterable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.account import Account
from app.models.enums import Role
from app.services.audit import set_actor

SESSION_COOKIE = "session"


def get_current_account(
    request: Request,
    db: Session = Depends(get_session),
) -> Account:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    claims = decode_access_token(token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    account = db.get(Account, int(claims["sub"]))
    if account is None or not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    # Anything this request changes is attributed to them.
    set_actor(db, account)

    # The role is re-read from the database rather than trusted from the token,
    # so a role change takes effect immediately instead of on token expiry.
    return account


def require_role(*roles: Role) -> Callable[..., Account]:
    """Every protected route declares its own access.

    The legacy application had no equivalent: authorization was the name of the
    folder a page was included from, and the AJAX endpoints behind it checked
    nothing at all.
    """
    allowed: Iterable[Role] = roles

    def dependency(account: Account = Depends(get_current_account)) -> Account:
        if account.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return account

    return dependency


require_admin = require_role(Role.admin)
require_faculty = require_role(Role.faculty)
require_student = require_role(Role.student)
require_staff = require_role(Role.admin, Role.faculty)

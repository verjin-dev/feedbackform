from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE, get_current_account
from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    verify_legacy_md5,
    verify_password,
)
from app.core.throttle import login_throttle
from app.models.account import Account
from app.schemas.auth import AccountOut, LoginRequest, PasswordChangeRequest

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# The session cookie is SameSite=Lax, which means the browser will not attach
# it to cross-site requests — that is what stands in for CSRF tokens here.
#
# The consequence is that the SPA must be same-origin with the API: a Vite dev
# proxy in development, and a single reverse proxy in production. A frontend
# served from a genuinely different origin would need SameSite=None, which
# requires HTTPS and brings CSRF tokens back. Same-origin is the simpler and
# safer arrangement, so it is the one this assumes.
def _issue_session(response: Response, account: Account) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_access_token(account.id, account.role),
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
    )


@router.post("/login", response_model=AccountOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
) -> Account:
    client_host = request.client.host if request.client else "unknown"
    throttle_key = f"{client_host}:{payload.email.lower()}"

    if login_throttle.is_blocked(throttle_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again in a few minutes.",
        )

    # Case-insensitive because addresses migrated from the PHP tables were
    # never normalised. A functional index on lower(email) is worth adding once
    # the account table is large enough for the scan to matter.
    account = db.scalar(
        select(Account).where(func.lower(Account.email) == payload.email.lower())
    )

    authenticated = False
    if account is not None and account.password_hash:
        authenticated = verify_password(account.password_hash, payload.password)
        if authenticated and needs_rehash(account.password_hash):
            account.password_hash = hash_password(payload.password)
    elif account is not None and account.legacy_md5:
        # First login since migration: accept the MD5 once, then replace it.
        authenticated = verify_legacy_md5(account.legacy_md5, payload.password)
        if authenticated:
            account.password_hash = hash_password(payload.password)
            account.legacy_md5 = None
    else:
        # No such account. Spend comparable time anyway so response latency
        # does not reveal which addresses exist.
        hash_password(payload.password)

    if account is None or not authenticated or not account.is_active:
        login_throttle.record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    db.commit()
    db.refresh(account)
    login_throttle.reset(throttle_key)
    _issue_session(response, account)
    return account


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)) -> Account:
    return account


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_session),
) -> None:
    if account.password_hash:
        valid = verify_password(account.password_hash, payload.current_password)
    elif account.legacy_md5:
        valid = verify_legacy_md5(account.legacy_md5, payload.current_password)
    else:
        valid = False

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    account.password_hash = hash_password(payload.new_password)
    account.legacy_md5 = None
    db.commit()
    db.refresh(account)

    # Re-issue so the change extends the session rather than leaving the user
    # on a cookie minted before it.
    _issue_session(response, account)

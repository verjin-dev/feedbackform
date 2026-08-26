"""The two ends of the college sign-in redirect.

The policy this file implements is short and is the whole security story:

  - An account is matched, never created. The directory decides who is a member
    of the college; an administrator decides who has an account here. Letting
    the first decide the second is how "anyone in the domain" becomes "anyone
    with a login".
  - Students are refused. The college issues directory accounts to staff only,
    so a token presenting a student's address is a mistake or an attack.
  - Password sign-in keeps working. An identity-provider outage during an
    evaluation window would otherwise lock the college out of its own feedback
    in the one week it cannot wait.

Everything else here is the mechanics of getting a browser there and back
without losing the thread.
"""

import secrets
from datetime import UTC, datetime
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.routes.auth import _issue_session
from app.core.database import get_session
from app.core.config import get_settings
from app.models import Account, ExternalIdentity, Role
from app.services import oidc
from app.services.audit import set_actor

router = APIRouter(prefix="/auth/sso", tags=["auth"])

STATE_COOKIE = "sso_state"

# Staff only, deliberately. See the module docstring.
ALLOWED_ROLES = {Role.admin, Role.faculty}


def _settings():
    return get_settings()


def _redirect_uri(request: Request) -> str:
    """Built from the incoming request rather than configured separately.

    A redirect_uri that disagrees with what was registered fails at the
    provider with a message nobody can act on; deriving it means the value sent
    at the start and the value sent at the exchange cannot drift apart, which
    is the failure that actually happens.
    """
    return str(request.url_for("sso_callback"))


def _app_url(path: str, **query: str) -> str:
    base = _settings().app_base_url.rstrip("/")
    if not query:
        return f"{base}{path}"
    pairs = "&".join(f"{key}={quote(value)}" for key, value in query.items())
    return f"{base}{path}?{pairs}"


def _fail(message: str) -> RedirectResponse:
    """Back to the sign-in page carrying the reason.

    Rendering an error here would leave the person on the API's origin with no
    way back into the application, which in practice means closing the tab and
    trying the whole thing again.
    """
    response = RedirectResponse(
        _app_url("/login", sso_error=message), status_code=status.HTTP_303_SEE_OTHER
    )
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


# --- Is it on? --------------------------------------------------------------


@router.get("/status")
def sso_status():
    """Read by the sign-in page before it offers the button.

    Unauthenticated on purpose: it is needed by somebody who is, by definition,
    not signed in yet. It says only whether the feature is on and what to call
    it, never the client id or the issuer.
    """
    settings = _settings()
    return {
        "enabled": settings.sso_enabled,
        "label": settings.oidc_button_label,
    }


# --- Out -------------------------------------------------------------------


@router.get("/start")
def sso_start(request: Request):
    settings = _settings()
    if not settings.sso_enabled:
        return _fail("College sign-in is not set up.")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = oidc.make_pkce()

    try:
        destination = oidc.authorization_url(
            redirect_uri=_redirect_uri(request),
            state=state,
            nonce=nonce,
            challenge=challenge,
        )
    except oidc.SsoError as error:
        return _fail(str(error))

    # State, nonce and verifier ride in one signed cookie rather than in server
    # memory: there is no session yet to hang them on, and a server-side store
    # would have to be shared across every worker to survive a callback landing
    # on a different one.
    envelope = jwt.encode(
        {
            "state": state,
            "nonce": nonce,
            "verifier": verifier,
            "exp": int(datetime.now(UTC).timestamp()) + oidc.STATE_TTL_SECONDS,
        },
        settings.secret_key,
        algorithm="HS256",
    )

    response = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        STATE_COOKIE,
        envelope,
        httponly=True,
        secure=settings.is_production,
        # Lax, not Strict: the browser arrives back here by top-level
        # navigation from the provider, and Strict would drop the cookie on
        # exactly that request -- making every sign-in fail as a state
        # mismatch.
        samesite="lax",
        max_age=oidc.STATE_TTL_SECONDS,
        path="/",
    )
    return response


# --- And back --------------------------------------------------------------


@router.get("/callback", name="sso_callback")
def sso_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_session),
):
    settings = _settings()
    if not settings.sso_enabled:
        return _fail("College sign-in is not set up.")

    if error:
        # The provider's own code ("access_denied" when somebody closes the
        # account chooser) is not a sentence anybody wants to read.
        return _fail("Sign-in was cancelled.")
    if not code or not state:
        return _fail("That sign-in did not complete. Please try again.")

    envelope = request.cookies.get(STATE_COOKIE)
    if not envelope:
        return _fail(
            "That sign-in took too long, or this browser blocked a cookie it "
            "needed. Please try again."
        )

    try:
        stored = jwt.decode(envelope, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return _fail("That sign-in could not be verified. Please try again.")

    # The whole point of state: a request that arrives without the value this
    # server issued is somebody else's, not this person's.
    if not secrets.compare_digest(str(stored.get("state", "")), state):
        return _fail("That sign-in could not be verified. Please try again.")

    try:
        token = oidc.exchange_code(
            code=code,
            redirect_uri=_redirect_uri(request),
            verifier=str(stored["verifier"]),
        )
        claims = oidc.verify(token, nonce=str(stored["nonce"]))
        oidc.check_domain(claims.email)
    except oidc.SsoError as failure:
        return _fail(str(failure))

    account = _match_account(db, claims)
    if isinstance(account, RedirectResponse):
        return account

    landing = RedirectResponse(
        _app_url("/"), status_code=status.HTTP_303_SEE_OTHER
    )
    _issue_session(landing, account)
    landing.delete_cookie(STATE_COOKIE, path="/")
    return landing


def _match_account(db: Session, claims: oidc.Claims):
    """Find the account this identity belongs to, or refuse.

    Returns either an Account or the redirect explaining why not.
    """
    identity = db.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == claims.issuer,
            ExternalIdentity.subject == claims.subject,
        )
    )

    if identity is not None:
        account = identity.account
        if account is None or not account.is_active:
            return _fail("That account is no longer active. Ask an administrator.")
        if account.role not in ALLOWED_ROLES:
            # A student account that somehow acquired a link. Refusing here as
            # well as at first link means a role change closes the door too.
            return _fail(
                "Students sign in with an email address and password, not with "
                "a college account."
            )
        identity.last_used_at = datetime.now(UTC)
        set_actor(db, account)
        db.commit()
        return account

    # First time: link to an account that already exists. Nothing is created.
    if not claims.email_verified:
        # Unverified, the address is a claim about somebody else's mailbox.
        return _fail(
            "The college sign-in service could not confirm that address. "
            "Sign in with your email address and password instead."
        )

    account = db.scalar(
        select(Account).where(Account.email == claims.email, Account.is_active.is_(True))
    )
    if account is None:
        # Deliberately not "no such account": for somebody who is in the
        # directory but has no account here, the actionable fact is that an
        # administrator has to make one.
        return _fail(
            "There is no account here for that address yet. Ask an "
            "administrator to add you."
        )

    if account.role not in ALLOWED_ROLES:
        return _fail(
            "Students sign in with an email address and password, not with a "
            "college account."
        )

    # The account already answers to a different directory identity. This is
    # what a reassigned address looks like: somebody left, their successor was
    # given the same address, and matching on it would hand the successor the
    # predecessor's account -- the exact takeover that keying on the subject
    # exists to prevent. Matching by address is only safe for an account that
    # has never been linked.
    existing = db.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == claims.issuer,
            ExternalIdentity.account_id == account.id,
        )
    )
    if existing is not None:
        return _fail(
            "That address is already linked to a different college account. "
            "An administrator needs to unlink it before you can sign in this "
            "way."
        )

    link = ExternalIdentity(
        provider=claims.issuer,
        subject=claims.subject,
        account_id=account.id,
        email_at_link=claims.email,
        last_used_at=datetime.now(UTC),
    )
    db.add(link)
    # Attributed to the person signing in: they are the one who linked it, and
    # a link appearing against "system" is the one an administrator would most
    # want explained.
    set_actor(db, account)
    db.commit()
    return account


# --- What an administrator can do about it ---------------------------------


@router.get("/links", response_model=list[dict])
def list_links(
    _admin: Account = Depends(require_admin),
    db: Session = Depends(get_session),
):
    """Every college directory account that can sign in as somebody here.

    Worth having on a screen rather than only in the audit log: the log says
    what changed, and this says what is true now, which is the question asked
    when somebody leaves.
    """
    rows = db.scalars(
        select(ExternalIdentity).order_by(ExternalIdentity.linked_at.desc())
    ).unique().all()
    return [
        {
            "id": row.id,
            "account_id": row.account_id,
            "account_name": row.account.full_name if row.account else "",
            "account_email": row.account.email if row.account else "",
            "email_at_link": row.email_at_link,
            "provider": row.provider,
            "linked_at": row.linked_at.isoformat() if row.linked_at else None,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            # The case the sign-in flow refuses and sends here: the directory
            # address no longer matches the account it is linked to, which is
            # what a reassigned address looks like.
            "stale": bool(row.account and row.account.email != row.email_at_link),
        }
        for row in rows
    ]


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink(
    link_id: int,
    _admin: Account = Depends(require_admin),
    db: Session = Depends(get_session),
) -> None:
    """Break the link, leaving the account alone.

    Deleting the account instead would be the wrong tool for a departure: the
    audit trail names them, and their teaching assignments are what past
    reports are built from. Password sign-in is unaffected, which is why this
    is safe to do the moment somebody is unsure about a link.
    """
    link = db.get(ExternalIdentity, link_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such link."
        )
    db.delete(link)
    db.commit()

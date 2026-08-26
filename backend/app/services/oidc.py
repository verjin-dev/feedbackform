"""College sign-in over OpenID Connect.

Configured by discovery URL rather than by provider name. Google Workspace and
Microsoft 365 are both standard OIDC and differ only in the discovery endpoint,
the credentials, and which domains count as the college -- all of which are
deployment configuration. Naming a provider in code would mean a rewrite if the
college moves between them, which colleges do.

What this deliberately does not do:

  - It never creates an account. A directory the application does not own
    deciding who exists in the application is how "anyone with an address in
    the domain" becomes "anyone with a login". Sign-in matches an account that
    an administrator already created, or it fails.
  - It never signs in a student. The college issues directory accounts to staff
    only, so a token presenting a student's address is either a mistake or an
    attack, and refusing costs nothing.
  - It never replaces password sign-in. An identity-provider outage during an
    evaluation window would otherwise lock the college out of its own feedback
    in the one week it cannot wait.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings

# Discovery and JWKS both change rarely and are fetched on a code path a person
# is waiting on, so both are cached for the process lifetime.
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_clients: dict[str, PyJWKClient] = {}

DISCOVERY_TTL_SECONDS = 60 * 60

# Long enough to sign in with a second factor and a password manager, short
# enough that a state cookie left on a shared machine is not a way in.
STATE_TTL_SECONDS = 15 * 60


class SsoError(Exception):
    """Anything that stops a sign-in.

    Carries a message written for the person who hit it, because these surface
    on a page they were redirected to rather than in a response to a request
    they made.
    """


@dataclass(frozen=True)
class Claims:
    issuer: str
    subject: str
    email: str
    email_verified: bool
    name: str | None


def discovery() -> dict[str, Any]:
    settings = get_settings()
    url = settings.oidc_discovery_url
    if not url:
        raise SsoError("College sign-in is not configured.")

    cached = _discovery_cache.get(url)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        document = response.json()
    except httpx.HTTPError as cause:
        raise SsoError("Could not reach the college sign-in service.") from cause

    for field in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        if field not in document:
            raise SsoError("The college sign-in service returned an unusable response.")

    _discovery_cache[url] = (time.monotonic() + DISCOVERY_TTL_SECONDS, document)
    return document


def _jwks_client(jwks_uri: str) -> PyJWKClient:
    client = _jwks_clients.get(jwks_uri)
    if client is None:
        client = PyJWKClient(jwks_uri, cache_keys=True)
        _jwks_clients[jwks_uri] = client
    return client


# --- Starting the flow ------------------------------------------------------


def make_pkce() -> tuple[str, str]:
    """A verifier and its challenge.

    PKCE on a confidential client is belt and braces, and it is the belt that
    holds when the braces are the part that leaks: an authorization code
    intercepted from the redirect is useless without the verifier, which never
    leaves this server.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def authorization_url(*, redirect_uri: str, state: str, nonce: str, challenge: str) -> str:
    settings = get_settings()
    document = discovery()

    parameters = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": redirect_uri,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # A hint, never a control: providers may ignore it, and the domain
        # check after the token comes back is what actually enforces this.
        "prompt": "select_account",
    }
    if len(settings.oidc_allowed_domains) == 1:
        # Google honours this and skips the account chooser for other domains.
        # Microsoft ignores it harmlessly.
        parameters["hd"] = settings.oidc_allowed_domains[0]

    return f"{document['authorization_endpoint']}?{urlencode(parameters)}"


# --- Finishing it -----------------------------------------------------------


def exchange_code(*, code: str, redirect_uri: str, verifier: str) -> str:
    """Swap the authorization code for an ID token. Returns the raw JWT."""
    settings = get_settings()
    document = discovery()

    try:
        response = httpx.post(
            document["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
    except httpx.HTTPError as cause:
        raise SsoError("Could not reach the college sign-in service.") from cause

    if response.status_code != 200:
        # The provider's own error text can name the client secret and is not
        # for the person signing in.
        raise SsoError("The college sign-in service rejected this sign-in.")

    token = response.json().get("id_token")
    if not token:
        raise SsoError("The college sign-in service returned no identity.")
    return token


def verify(token: str, *, nonce: str) -> Claims:
    """Validate the ID token and return what it asserts.

    Signature, issuer, audience, expiry and nonce are all checked. The nonce is
    the one that is easy to leave out and is the one that stops a token minted
    for a different sign-in being replayed into this one.
    """
    settings = get_settings()
    document = discovery()

    try:
        key = _jwks_client(document["jwks_uri"]).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_client_id,
            issuer=document["issuer"],
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as cause:
        raise SsoError("That sign-in could not be verified.") from cause

    if not secrets.compare_digest(str(payload.get("nonce", "")), nonce):
        raise SsoError("That sign-in could not be verified.")

    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise SsoError("The college sign-in service did not supply an address.")

    return Claims(
        issuer=str(payload["iss"]),
        subject=str(payload["sub"]),
        email=email,
        # Microsoft omits the claim on some tenants; absent is not verified.
        email_verified=bool(payload.get("email_verified", False)),
        name=payload.get("name"),
    )


def check_domain(email: str) -> None:
    """Refuse an address outside the college.

    Both providers will happily authenticate a personal account against a
    client that allows it. This check, not the provider, is what makes this
    "the college's directory" rather than "anyone with a Google account".
    """
    settings = get_settings()
    domain = email.rsplit("@", 1)[-1].lower()
    allowed = {value.strip().lower().lstrip("@") for value in settings.oidc_allowed_domains}
    if domain not in allowed:
        raise SsoError(
            "That account is not part of the college directory. "
            "Sign in with your email address and password instead."
        )

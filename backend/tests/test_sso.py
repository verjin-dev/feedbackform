"""College sign-in over OpenID Connect.

The mechanics are ordinary. The policy is not, and it is what these test:

  - An account is matched, never created.
  - Students are refused.
  - Password sign-in keeps working.

The provider is faked at the two seams that touch the network -- discovery and
the token exchange -- rather than by driving a real Google or Microsoft tenant.
What is verified for real is everything after the token arrives: the nonce, the
state, the domain, and which account a subject resolves to.
"""

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.api.routes import sso as sso_routes
from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Account, ExternalIdentity, Role
from app.services import oidc

ISSUER = "https://accounts.example-college.test"
CLIENT_ID = "test-client-id"
DOMAIN = "example.edu"
PASSWORD = "sso-tests-password"

# A real RSA key, because `verify` accepts RS256 and ES256 only and must keep
# doing so: accepting HS256 alongside them is the algorithm-confusion attack,
# where a token is signed with the provider's *public* key as an HMAC secret
# and verifies. Generated once for the module -- 2048 bits is a second.
PROVIDER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PROVIDER_PUBLIC_KEY = PROVIDER_PRIVATE_KEY.public_key()

DISCOVERY = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/authorize",
    "token_endpoint": f"{ISSUER}/token",
    "jwks_uri": f"{ISSUER}/jwks",
}


@pytest.fixture
def sso_settings(monkeypatch):
    """Turn the feature on for the process, and off again afterwards."""
    settings = get_settings()
    monkeypatch.setattr(settings, "oidc_discovery_url", f"{ISSUER}/.well-known", False)
    monkeypatch.setattr(settings, "oidc_client_id", CLIENT_ID, False)
    monkeypatch.setattr(settings, "oidc_client_secret", "test-secret", False)
    monkeypatch.setattr(settings, "oidc_allowed_domains", [DOMAIN], False)
    monkeypatch.setattr(oidc, "discovery", lambda: DISCOVERY)
    return settings


def id_token(
    *,
    subject: str,
    email: str,
    nonce: str,
    email_verified: bool = True,
    audience: str = CLIENT_ID,
    issuer: str = ISSUER,
    expired: bool = False,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "email": email,
            "email_verified": email_verified,
            "nonce": nonce,
            "iat": int(now.timestamp()),
            "exp": int(
                (now - timedelta(minutes=5) if expired else now + timedelta(minutes=5))
                .timestamp()
            ),
        },
        PROVIDER_PRIVATE_KEY,
        algorithm="RS256",
    )


@pytest.fixture
def fake_provider(monkeypatch, sso_settings):
    """Stands in for the two calls that would leave this machine."""
    issued: dict[str, str] = {}

    monkeypatch.setattr(oidc, "_jwks_client", lambda uri: _StubJwks())
    monkeypatch.setattr(
        oidc,
        "exchange_code",
        lambda *, code, redirect_uri, verifier: issued[code],
    )
    return issued


class _StubJwks:
    """Stands in for fetching the provider's JWKS."""

    def get_signing_key_from_jwt(self, token):
        class Key:
            key = PROVIDER_PUBLIC_KEY

        return Key()


def staff(session, email=f"asha.raman@{DOMAIN}", role=Role.faculty) -> Account:
    account = Account(
        role=role,
        school_id=secrets.token_hex(4),
        first_name="Asha",
        last_name="Raman",
        email=email,
        password_hash=hash_password(PASSWORD),
    )
    session.add(account)
    session.commit()
    return account


def sign_in_via_sso(client, session, fake_provider, *, subject, email, **token_kwargs):
    """Drive the real /start and /callback, with the network faked."""
    start = client.get("/auth/sso/start", follow_redirects=False)
    assert start.status_code == 303, start.text

    envelope = start.cookies.get(sso_routes.STATE_COOKIE) or client.cookies.get(
        sso_routes.STATE_COOKIE
    )
    stored = jwt.decode(
        envelope, get_settings().secret_key, algorithms=["HS256"]
    )

    code = secrets.token_urlsafe(8)
    fake_provider[code] = id_token(
        subject=subject,
        email=email,
        nonce=token_kwargs.pop("nonce", stored["nonce"]),
        **token_kwargs,
    )
    return client.get(
        f"/auth/sso/callback?code={code}&state={stored['state']}",
        follow_redirects=False,
    )


def landed_signed_in(response) -> bool:
    return "session=" in response.headers.get("set-cookie", "")


def as_admin(admin_client):
    """Sign the administrator back in.

    `client` and `admin_client` wrap the same underlying client, so a sign-in
    performed through one replaces the session cookie for both -- and the
    administrator silently becomes whoever signed in last. Every check below
    that needs admin rights re-establishes them explicitly.
    """
    admin_client.post("/auth/logout")
    response = admin_client.post(
        "/auth/login",
        json={"email": "root.admin@example.edu", "password": "conftest-admin-password"},
    )
    assert response.status_code == 200, response.text
    return admin_client


def failure_message(response) -> str:
    return unquote(response.headers.get("location", ""))


class TestWhenItIsOff:
    def test_the_sign_in_page_is_told_it_is_off(self, client):
        assert client.get("/auth/sso/status").json()["enabled"] is False

    def test_starting_a_sign_in_goes_nowhere(self, client):
        response = client.get("/auth/sso/start", follow_redirects=False)
        assert response.status_code == 303
        assert "not set up" in failure_message(response)

    def test_the_status_endpoint_leaks_no_configuration(self, client, sso_settings):
        body = client.get("/auth/sso/status").json()
        assert body["enabled"] is True
        assert CLIENT_ID not in str(body)
        assert ISSUER not in str(body)


class TestStartingTheFlow:
    def test_it_redirects_to_the_provider_with_pkce(self, client, sso_settings):
        response = client.get("/auth/sso/start", follow_redirects=False)
        destination = response.headers["location"]

        assert destination.startswith(f"{ISSUER}/authorize")
        assert "code_challenge=" in destination
        assert "code_challenge_method=S256" in destination
        assert "response_type=code" in destination

    def test_the_verifier_never_goes_to_the_provider(self, client, sso_settings):
        """An authorization code intercepted from the redirect is useless
        without the verifier, which is the point of sending only its hash."""
        response = client.get("/auth/sso/start", follow_redirects=False)
        stored = jwt.decode(
            response.cookies[sso_routes.STATE_COOKIE],
            get_settings().secret_key,
            algorithms=["HS256"],
        )
        assert stored["verifier"] not in response.headers["location"]

    def test_the_state_cookie_survives_the_return_trip(self, client, sso_settings):
        """SameSite=Strict would be dropped on the top-level navigation back
        from the provider, making every sign-in fail as a state mismatch."""
        response = client.get("/auth/sso/start", follow_redirects=False)
        header = response.headers["set-cookie"]
        assert "samesite=lax" in header.lower()
        assert "httponly" in header.lower()


class TestMatchingAnAccount:
    def test_a_known_staff_address_signs_in(
        self, client, session, fake_provider
    ):
        account = staff(session)
        response = sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )

        assert landed_signed_in(response), failure_message(response)
        assert client.get("/auth/me").json()["email"] == account.email

    def test_the_link_is_recorded_against_the_account(
        self, client, session, fake_provider
    ):
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )

        [link] = session.query(ExternalIdentity).all()
        assert link.account_id == account.id
        assert link.subject == "dir-1"
        assert link.email_at_link == account.email

    def test_no_account_is_created_for_an_unknown_address(
        self, client, session, fake_provider
    ):
        """The directory decides who is a member of the college; an
        administrator decides who has an account here. Letting the first decide
        the second is how "anyone in the domain" becomes "anyone with a
        login"."""
        before = session.query(Account).count()

        response = sign_in_via_sso(
            client,
            session,
            fake_provider,
            subject="dir-new",
            email=f"stranger@{DOMAIN}",
        )

        assert not landed_signed_in(response)
        assert "no account here" in failure_message(response)
        assert session.query(Account).count() == before

    def test_a_student_is_refused(self, client, session, fixtures, fake_provider):
        """The college issues directory accounts to staff only, so a token
        presenting a student's address is a mistake or an attack."""
        student = fixtures["student"]
        student.email = f"karthik.iyer@{DOMAIN}"
        session.commit()

        response = sign_in_via_sso(
            client, session, fake_provider, subject="dir-s", email=student.email
        )

        assert not landed_signed_in(response)
        assert session.query(ExternalIdentity).count() == 0

    def test_a_student_is_still_refused_after_a_role_change(
        self, client, session, fixtures, fake_provider
    ):
        """Linked as staff, then moved to a student account: the door closes
        again rather than staying open on the strength of the old link."""
        account = staff(session, email=f"moved@{DOMAIN}")
        first = sign_in_via_sso(
            client, session, fake_provider, subject="dir-m", email=account.email
        )
        assert landed_signed_in(first)

        client.post("/auth/logout")
        # Class first: the check constraint fires on autoflush, and a
        # student without a class is exactly what it exists to refuse.
        account.class_group_id = fixtures["class_group"].id
        account.role = Role.student
        session.commit()

        second = sign_in_via_sso(
            client, session, fake_provider, subject="dir-m", email=account.email
        )
        assert not landed_signed_in(second)

    def test_a_deactivated_account_cannot_sign_in(
        self, client, session, fake_provider
    ):
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )
        client.post("/auth/logout")

        account.is_active = False
        session.commit()

        response = sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )
        assert not landed_signed_in(response)

    def test_a_reassigned_address_does_not_inherit_the_account(
        self, client, session, fake_provider
    ):
        """An address gets reassigned when somebody leaves and their successor
        is given the same one. Matching on the address alone would hand that
        successor their predecessor's account, which is the takeover keying on
        the subject exists to prevent -- so first-use address matching applies
        only to an account that has never been linked."""
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-original", email=account.email
        )
        client.post("/auth/logout")

        # Same address, different person in the directory.
        response = sign_in_via_sso(
            client, session, fake_provider, subject="dir-successor", email=account.email
        )

        assert not landed_signed_in(response)
        assert "administrator" in failure_message(response)

        subjects = {row.subject for row in session.query(ExternalIdentity).all()}
        assert subjects == {"dir-original"}


class TestRefusingWhatItShould:
    def test_an_address_outside_the_college_is_refused(
        self, client, session, fake_provider
    ):
        """Both providers will happily authenticate a personal account. The
        domain check, not the provider, is what makes this the college's
        directory rather than anyone's."""
        staff(session, email="asha.raman@gmail.com")

        response = sign_in_via_sso(
            client,
            session,
            fake_provider,
            subject="dir-x",
            email="asha.raman@gmail.com",
        )
        assert not landed_signed_in(response)
        assert session.query(ExternalIdentity).count() == 0

    def test_an_unverified_address_is_refused(
        self, client, session, fake_provider
    ):
        """Unverified, the address is a claim about somebody else's mailbox."""
        account = staff(session)

        response = sign_in_via_sso(
            client,
            session,
            fake_provider,
            subject="dir-1",
            email=account.email,
            email_verified=False,
        )
        assert not landed_signed_in(response)
        assert session.query(ExternalIdentity).count() == 0

    def test_a_replayed_nonce_is_refused(self, client, session, fake_provider):
        """The check that is easy to leave out, and the one that stops a token
        minted for a different sign-in being replayed into this one."""
        account = staff(session)

        response = sign_in_via_sso(
            client,
            session,
            fake_provider,
            subject="dir-1",
            email=account.email,
            nonce="a-nonce-from-some-other-sign-in",
        )
        assert not landed_signed_in(response)

    def test_a_mismatched_state_is_refused(self, client, session, fake_provider):
        staff(session)
        client.get("/auth/sso/start", follow_redirects=False)

        response = client.get(
            "/auth/sso/callback?code=anything&state=not-the-issued-state",
            follow_redirects=False,
        )
        assert not landed_signed_in(response)

    def test_a_callback_with_no_state_cookie_is_refused(
        self, client, sso_settings
    ):
        response = client.get(
            "/auth/sso/callback?code=anything&state=anything",
            follow_redirects=False,
        )
        assert not landed_signed_in(response)

    def test_a_token_for_another_audience_is_refused(
        self, client, session, fake_provider
    ):
        account = staff(session)

        response = sign_in_via_sso(
            client,
            session,
            fake_provider,
            subject="dir-1",
            email=account.email,
            audience="some-other-application",
        )
        assert not landed_signed_in(response)

    def test_an_expired_token_is_refused(self, client, session, fake_provider):
        account = staff(session)

        response = sign_in_via_sso(
            client,
            session,
            fake_provider,
            subject="dir-1",
            email=account.email,
            expired=True,
        )
        assert not landed_signed_in(response)

    def test_a_token_from_another_issuer_is_refused(
        self, client, session, fake_provider
    ):
        account = staff(session)

        response = sign_in_via_sso(
            client,
            session,
            fake_provider,
            subject="dir-1",
            email=account.email,
            issuer="https://accounts.somewhere-else.test",
        )
        assert not landed_signed_in(response)

    def test_a_cancelled_sign_in_says_so_plainly(self, client, sso_settings):
        response = client.get(
            "/auth/sso/callback?error=access_denied", follow_redirects=False
        )
        assert "cancelled" in failure_message(response).lower()


class TestPasswordsKeepWorking:
    def test_a_linked_account_can_still_use_its_password(
        self, client, session, fake_provider
    ):
        """An identity-provider outage during an evaluation window would
        otherwise lock the college out of its own feedback in the one week it
        cannot wait."""
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )
        client.post("/auth/logout")

        response = client.post(
            "/auth/login", json={"email": account.email, "password": PASSWORD}
        )
        assert response.status_code == 200

    def test_students_sign_in_exactly_as_before(
        self, client, session, fixtures, sso_settings
    ):
        student = fixtures["student"]
        student.password_hash = hash_password(PASSWORD)
        session.commit()

        response = client.post(
            "/auth/login", json={"email": student.email, "password": PASSWORD}
        )
        assert response.status_code == 200


class TestItIsInTheAuditLog:
    def test_linking_an_identity_is_recorded(
        self, client, session, fake_provider
    ):
        """Which directory account may sign in as which account here is an
        access change, and the log exists for those."""
        from app.models import AuditEvent

        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )

        [entry] = (
            session.query(AuditEvent).filter_by(entity_type="ExternalIdentity").all()
        )
        assert entry.action == "created"
        assert account.email in entry.summary
        assert entry.actor_email == account.email

    def test_signing_in_again_does_not_fill_the_log(
        self, client, session, fake_provider
    ):
        """last_used_at moves on every sign-in. A row for each would bury the
        one change anybody wants to find."""
        from app.models import AuditEvent

        account = staff(session)
        for _ in range(3):
            sign_in_via_sso(
                client, session, fake_provider, subject="dir-1", email=account.email
            )
            client.post("/auth/logout")

        entries = session.query(AuditEvent).filter_by(
            entity_type="ExternalIdentity"
        ).all()
        assert len(entries) == 1


class TestWhatAnAdministratorCanDo:
    def test_the_links_are_listed(self, client, session, fake_provider, admin_client):
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )

        [row] = as_admin(admin_client).get("/auth/sso/links").json()
        assert row["account_email"] == account.email
        assert row["stale"] is False

    def test_a_reassigned_address_shows_as_stale(
        self, client, session, fake_provider, admin_client
    ):
        """What a departure looks like on the screen: the link still works, but
        the address it was made with is no longer the account's."""
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )

        account.email = f"asha.raman.retired@{DOMAIN}"
        session.commit()

        [row] = as_admin(admin_client).get("/auth/sso/links").json()
        assert row["stale"] is True

    def test_unlinking_leaves_the_account_alone(
        self, client, session, fake_provider, admin_client
    ):
        """Deleting the account would be the wrong tool for a departure: the
        audit trail names them, and their assignments are what past reports are
        built from."""
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )
        [row] = as_admin(admin_client).get("/auth/sso/links").json()

        assert (
            as_admin(admin_client).delete(f"/auth/sso/links/{row['id']}").status_code
            == 204
        )
        assert session.query(ExternalIdentity).count() == 0
        assert session.get(Account, account.id) is not None

    def test_an_unlinked_person_can_still_use_their_password(
        self, client, session, fake_provider, admin_client
    ):
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-1", email=account.email
        )
        [row] = as_admin(admin_client).get("/auth/sso/links").json()
        as_admin(admin_client).delete(f"/auth/sso/links/{row['id']}")

        client.post("/auth/logout")
        response = client.post(
            "/auth/login", json={"email": account.email, "password": PASSWORD}
        )
        assert response.status_code == 200

    def test_unlinking_frees_the_account_to_be_linked_again(
        self, client, session, fake_provider, admin_client
    ):
        """The path out of the refusal the sign-in flow sends people here for:
        unlink, and the successor's first sign-in links cleanly."""
        account = staff(session)
        sign_in_via_sso(
            client, session, fake_provider, subject="dir-original", email=account.email
        )
        [row] = as_admin(admin_client).get("/auth/sso/links").json()
        as_admin(admin_client).delete(f"/auth/sso/links/{row['id']}")

        client.post("/auth/logout")
        response = sign_in_via_sso(
            client, session, fake_provider, subject="dir-successor", email=account.email
        )
        assert landed_signed_in(response), failure_message(response)

    def test_faculty_cannot_read_the_links(self, client, session, fake_provider):
        account = staff(session)
        client.post(
            "/auth/login", json={"email": account.email, "password": PASSWORD}
        )
        assert client.get("/auth/sso/links").status_code == 403

    def test_an_anonymous_caller_cannot_read_the_links(self, client, sso_settings):
        assert client.get("/auth/sso/links").status_code == 401

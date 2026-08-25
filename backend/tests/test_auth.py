import hashlib

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_staff
from app.core.security import hash_password
from app.main import app
from app.models import Account, Role

PASSWORD = "correct-horse-battery-staple"
LEGACY_PASSWORD = "admin123"


# Probe routes, registered on the real app so the role dependencies are
# exercised exactly as a real route would use them.
@app.get("/_test/admin-only")
def _admin_only(account: Account = Depends(require_admin)) -> dict:
    return {"id": account.id}


@app.get("/_test/staff-only")
def _staff_only(account: Account = Depends(require_staff)) -> dict:
    return {"id": account.id}


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


@pytest.fixture
def admin(session: Session) -> Account:
    account = Account(
        role=Role.admin,
        first_name="Priya",
        last_name="Menon",
        email="Priya.Menon@example.edu",
        password_hash=hash_password(PASSWORD),
    )
    session.add(account)
    session.commit()
    return account


@pytest.fixture
def migrated_admin(session: Session) -> Account:
    """An account as it arrives from the PHP database: MD5 only, no Argon2."""
    account = Account(
        role=Role.admin,
        first_name="Legacy",
        last_name="Admin",
        email="legacy@example.edu",
        password_hash=None,
        legacy_md5=hashlib.md5(LEGACY_PASSWORD.encode()).hexdigest(),
    )
    session.add(account)
    session.commit()
    return account


class TestLogin:
    def test_valid_credentials_return_the_account(self, client, admin):
        response = _login(client, "priya.menon@example.edu", PASSWORD)

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "Priya.Menon@example.edu"
        assert body["role"] == "admin"
        assert body["full_name"] == "Priya Menon"

    def test_email_matching_is_case_insensitive(self, client, admin):
        """Addresses migrated from the PHP tables were never normalised."""
        assert _login(client, "PRIYA.MENON@EXAMPLE.EDU", PASSWORD).status_code == 200

    def test_no_password_material_is_ever_returned(self, client, admin):
        body = _login(client, "priya.menon@example.edu", PASSWORD).json()
        assert not {"password", "password_hash", "legacy_md5"} & set(body)

    def test_session_cookie_is_httponly_and_samesite(self, client, admin):
        response = _login(client, "priya.menon@example.edu", PASSWORD)
        set_cookie = response.headers["set-cookie"].lower()

        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie

    def test_wrong_password_is_rejected(self, client, admin):
        assert _login(client, "priya.menon@example.edu", "wrong").status_code == 401

    def test_unknown_account_gives_the_same_answer_as_a_wrong_password(
        self, client, admin
    ):
        """Distinguishable responses would confirm which addresses exist."""
        unknown = _login(client, "nobody@example.edu", PASSWORD)
        wrong = _login(client, "priya.menon@example.edu", "wrong")

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]

    def test_a_deactivated_account_cannot_log_in(self, client, admin, session):
        admin.is_active = False
        session.commit()

        assert _login(client, "priya.menon@example.edu", PASSWORD).status_code == 401

    def test_the_role_is_not_taken_from_the_request(self, client, admin):
        """The legacy form sent an index that selected which table to
        authenticate against. Extra fields must not influence the result."""
        response = client.post(
            "/auth/login",
            json={
                "email": "priya.menon@example.edu",
                "password": PASSWORD,
                "role": "student",
                "login": 3,
            },
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"


class TestLegacyPasswordUpgrade:
    def test_a_migrated_account_can_log_in_with_its_md5_password(
        self, client, migrated_admin
    ):
        assert _login(client, "legacy@example.edu", LEGACY_PASSWORD).status_code == 200

    def test_logging_in_replaces_the_md5_with_argon2(
        self, client, migrated_admin, session
    ):
        _login(client, "legacy@example.edu", LEGACY_PASSWORD)
        session.refresh(migrated_admin)

        assert migrated_admin.legacy_md5 is None
        assert migrated_admin.password_hash is not None
        assert migrated_admin.password_hash.startswith("$argon2id$")
        assert migrated_admin.needs_password_upgrade is False

    def test_the_same_password_still_works_after_the_upgrade(
        self, client, migrated_admin
    ):
        _login(client, "legacy@example.edu", LEGACY_PASSWORD)

        assert _login(client, "legacy@example.edu", LEGACY_PASSWORD).status_code == 200

    def test_a_wrong_password_does_not_trigger_an_upgrade(
        self, client, migrated_admin, session
    ):
        _login(client, "legacy@example.edu", "not-the-password")
        session.refresh(migrated_admin)

        assert migrated_admin.legacy_md5 is not None
        assert migrated_admin.password_hash is None


class TestSession:
    def test_me_requires_a_session(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_me_returns_the_logged_in_account(self, client, admin):
        _login(client, "priya.menon@example.edu", PASSWORD)

        response = client.get("/auth/me")
        assert response.status_code == 200
        assert response.json()["id"] == admin.id

    def test_logout_ends_the_session(self, client, admin):
        _login(client, "priya.menon@example.edu", PASSWORD)
        assert client.post("/auth/logout").status_code == 204

        assert client.get("/auth/me").status_code == 401

    def test_a_forged_cookie_is_rejected(self, client, admin):
        client.cookies.set("session", "not.a.real.token")

        assert client.get("/auth/me").status_code == 401


class TestRoleGuards:
    def test_an_admin_reaches_an_admin_route(self, client, admin):
        _login(client, "priya.menon@example.edu", PASSWORD)

        assert client.get("/_test/admin-only").status_code == 200

    def test_a_student_is_refused_an_admin_route(self, client, fixtures, session):
        student = fixtures["student"]
        student.password_hash = hash_password(PASSWORD)
        session.commit()
        _login(client, student.email, PASSWORD)

        response = client.get("/_test/admin-only")
        assert response.status_code == 403

    def test_an_anonymous_caller_gets_401_not_403(self, client):
        """401 means "who are you", 403 means "not you". Conflating them makes
        an expired session look like a permissions bug."""
        assert client.get("/_test/admin-only").status_code == 401

    def test_faculty_reach_a_staff_route_but_not_an_admin_one(
        self, client, fixtures, session
    ):
        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password(PASSWORD)
        session.commit()
        _login(client, faculty.email, PASSWORD)

        assert client.get("/_test/staff-only").status_code == 200
        assert client.get("/_test/admin-only").status_code == 403


class TestThrottle:
    def test_repeated_failures_are_throttled(self, client, admin):
        for _ in range(10):
            assert _login(client, "priya.menon@example.edu", "wrong").status_code == 401

        response = _login(client, "priya.menon@example.edu", "wrong")
        assert response.status_code == 429

    def test_the_throttle_blocks_the_correct_password_too(self, client, admin):
        """Otherwise it would only slow down attackers who never succeed."""
        for _ in range(10):
            _login(client, "priya.menon@example.edu", "wrong")

        assert _login(client, "priya.menon@example.edu", PASSWORD).status_code == 429

    def test_success_clears_the_counter(self, client, admin):
        for _ in range(9):
            _login(client, "priya.menon@example.edu", "wrong")
        assert _login(client, "priya.menon@example.edu", PASSWORD).status_code == 200

        for _ in range(9):
            _login(client, "priya.menon@example.edu", "wrong")
        assert _login(client, "priya.menon@example.edu", PASSWORD).status_code == 200


class TestPasswordChange:
    def test_changing_a_password_requires_the_current_one(self, client, admin):
        _login(client, "priya.menon@example.edu", PASSWORD)

        response = client.post(
            "/auth/me/password",
            json={"current_password": "wrong", "new_password": "a-brand-new-secret"},
        )
        assert response.status_code == 400

    def test_a_changed_password_replaces_the_old_one(self, client, admin):
        _login(client, "priya.menon@example.edu", PASSWORD)
        new_password = "a-different-long-secret"

        response = client.post(
            "/auth/me/password",
            json={"current_password": PASSWORD, "new_password": new_password},
        )
        assert response.status_code == 204

        client.post("/auth/logout")
        assert _login(client, "priya.menon@example.edu", PASSWORD).status_code == 401
        assert _login(client, "priya.menon@example.edu", new_password).status_code == 200

    def test_short_passwords_are_refused(self, client, admin):
        _login(client, "priya.menon@example.edu", PASSWORD)

        response = client.post(
            "/auth/me/password",
            json={"current_password": PASSWORD, "new_password": "short"},
        )
        assert response.status_code == 422

    def test_a_migrated_account_can_change_from_its_md5_password(
        self, client, migrated_admin, session
    ):
        _login(client, "legacy@example.edu", LEGACY_PASSWORD)

        response = client.post(
            "/auth/me/password",
            json={
                "current_password": LEGACY_PASSWORD,
                "new_password": "a-proper-long-password",
            },
        )
        assert response.status_code == 204

        session.refresh(migrated_admin)
        assert migrated_admin.legacy_md5 is None

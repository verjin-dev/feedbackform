"""Password reset by email.

The system had no outbound mail at all, which is why migrated accounts were
given a rehash-on-login path rather than a forced reset: there was no way to
tell anyone. These cover the flow and the two things it must not do — confirm
whether an address exists, and let a link be used twice.
"""

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import Account, Role

PASSWORD = "the-original-password"
NEW_PASSWORD = "a-brand-new-password"


@pytest.fixture
def person(session: Session) -> Account:
    account = Account(
        role=Role.faculty,
        first_name="Asha",
        last_name="Raman",
        email="asha.reset@example.edu",
        password_hash=hash_password(PASSWORD),
    )
    session.add(account)
    session.commit()
    return account


def request_reset(client, email: str):
    return client.post("/auth/password-reset/request", json={"email": email})


def token_from(outbox, email: str) -> str:
    [message] = [m for m in outbox if m.to == email]
    return message.body.split("/reset-password?token=")[1].split()[0]


class TestRequesting:
    def test_a_known_address_receives_a_link(self, client, person, outbox):
        assert request_reset(client, person.email).status_code == 202

        [message] = outbox
        assert message.to == person.email
        assert "/reset-password?token=" in message.body
        assert "Reset your Faculty Evaluation password" in message.subject

    def test_an_unknown_address_answers_identically(self, client, person, outbox):
        """Anything else turns this into an account enumeration endpoint."""
        known = request_reset(client, person.email)
        unknown = request_reset(client, "nobody@example.edu")

        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        # ...and no mail was sent for the address that does not exist.
        assert [m.to for m in outbox] == [person.email]

    def test_a_deactivated_account_is_not_mailed_but_looks_the_same(
        self, client, person, session, outbox
    ):
        person.is_active = False
        session.commit()

        assert request_reset(client, person.email).status_code == 202
        assert outbox == []

    def test_the_address_is_matched_case_insensitively(self, client, person, outbox):
        assert request_reset(client, "ASHA.RESET@Example.EDU").status_code == 202
        assert len(outbox) == 1

    def test_repeated_requests_are_throttled(self, client, person, outbox):
        """Without this, anyone can mail-bomb a known address for free."""
        for _ in range(10):
            request_reset(client, person.email)

        before = len(outbox)
        request_reset(client, person.email)
        assert len(outbox) == before

    def test_being_throttled_still_looks_like_success(self, client, person):
        for _ in range(12):
            last = request_reset(client, person.email)

        assert last.status_code == 202


class TestRedeeming:
    def test_a_valid_link_sets_the_new_password(
        self, client, person, session, outbox
    ):
        request_reset(client, person.email)
        token = token_from(outbox, person.email)

        response = client.post(
            "/auth/password-reset/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 204

        session.refresh(person)
        assert verify_password(person.password_hash, NEW_PASSWORD)

    def test_the_old_password_stops_working(self, client, person, outbox):
        request_reset(client, person.email)
        client.post(
            "/auth/password-reset/confirm",
            json={"token": token_from(outbox, person.email), "new_password": NEW_PASSWORD},
        )

        assert (
            client.post(
                "/auth/login", json={"email": person.email, "password": PASSWORD}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/auth/login", json={"email": person.email, "password": NEW_PASSWORD}
            ).status_code
            == 200
        )

    def test_a_link_cannot_be_used_twice(self, client, person, outbox):
        """The fingerprint in the token stops matching the moment the password
        changes — including when this very link changed it."""
        request_reset(client, person.email)
        token = token_from(outbox, person.email)

        first = client.post(
            "/auth/password-reset/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        second = client.post(
            "/auth/password-reset/confirm",
            json={"token": token, "new_password": "yet-another-password"},
        )

        assert first.status_code == 204
        assert second.status_code == 400
        assert "already been used" in second.json()["detail"]

    def test_changing_the_password_elsewhere_kills_an_outstanding_link(
        self, client, person, session, outbox
    ):
        request_reset(client, person.email)
        token = token_from(outbox, person.email)

        # The user remembers their password and changes it the normal way.
        client.post("/auth/login", json={"email": person.email, "password": PASSWORD})
        client.post(
            "/auth/me/password",
            json={"current_password": PASSWORD, "new_password": "changed-in-settings"},
        )
        client.post("/auth/logout")

        stale = client.post(
            "/auth/password-reset/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert stale.status_code == 400

    def test_a_forged_token_is_refused(self, client, person):
        response = client.post(
            "/auth/password-reset/confirm",
            json={"token": "not.a.real.token", "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 400

    def test_an_invitation_token_cannot_be_replayed_as_a_reset(
        self, client, person, session
    ):
        """Tokens carry their purpose, so one kind of link is not another."""
        from app.services.notifications import invitation_token

        token = invitation_token(person)
        response = client.post(
            "/auth/password-reset/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 400

    def test_a_short_password_is_refused(self, client, person, outbox):
        request_reset(client, person.email)
        response = client.post(
            "/auth/password-reset/confirm",
            json={"token": token_from(outbox, person.email), "new_password": "short"},
        )
        assert response.status_code == 422

    def test_redeeming_does_not_sign_the_user_in(self, client, person, outbox):
        """Controlling the mailbox is not the same as being the account holder;
        the next step is a login they can confirm the new password with."""
        request_reset(client, person.email)
        client.post(
            "/auth/password-reset/confirm",
            json={"token": token_from(outbox, person.email), "new_password": NEW_PASSWORD},
        )

        assert client.get("/auth/me").status_code == 401

    def test_a_migrated_account_can_reset_away_its_md5(
        self, client, session, outbox
    ):
        import hashlib

        account = Account(
            role=Role.student,
            first_name="Legacy",
            last_name="Student",
            email="legacy.reset@example.edu",
            password_hash=None,
            legacy_md5=hashlib.md5(b"admin123").hexdigest(),
            class_group_id=None,
        )
        # Students need a class; this one is faculty-shaped for the test.
        account.role = Role.faculty
        session.add(account)
        session.commit()

        request_reset(client, account.email)
        client.post(
            "/auth/password-reset/confirm",
            json={
                "token": token_from(outbox, account.email),
                "new_password": NEW_PASSWORD,
            },
        )

        session.refresh(account)
        assert account.legacy_md5 is None
        assert account.password_hash.startswith("$argon2id$")


class TestChecking:
    def test_a_good_link_reports_who_it_is_for(self, client, person, outbox):
        request_reset(client, person.email)
        token = token_from(outbox, person.email)

        response = client.get("/auth/password-reset/check", params={"token": token})
        assert response.json() == {
            "valid": True,
            "email": person.email,
            "first_name": "Asha",
        }

    def test_a_spent_link_reports_invalid_without_leaking_the_address(
        self, client, person, outbox
    ):
        request_reset(client, person.email)
        token = token_from(outbox, person.email)
        client.post(
            "/auth/password-reset/confirm",
            json={"token": token, "new_password": NEW_PASSWORD},
        )

        response = client.get("/auth/password-reset/check", params={"token": token})
        assert response.json() == {"valid": False, "email": None, "first_name": None}


class TestConsoleBackend:
    def test_the_console_backend_actually_emits(self, client, person, caplog):
        """It exists to be seen. Logging it below the effective level makes an
        unconfigured deployment silent, which is the failure it replaces."""
        import logging

        from app.core.email import ConsoleMailer, set_mailer

        set_mailer(ConsoleMailer())
        try:
            with caplog.at_level(logging.INFO, logger="app.core.email"):
                request_reset(client, person.email)
        finally:
            set_mailer(None)

        assert "/reset-password?token=" in caplog.text

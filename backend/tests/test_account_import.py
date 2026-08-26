"""Bulk CSV import.

The file an administrator actually uploads came out of a spreadsheet, so these
cover a byte-order mark, renamed headings, blank lines and duplicate rows
alongside the happy path.
"""

from sqlalchemy.orm import Session

from app.models import Account

HEADER = "role,first_name,last_name,email,school_id,curriculum,level,section\n"


def upload(client, body: str, **params):
    return client.post(
        "/accounts/import",
        files={"file": ("roll.csv", body.encode("utf-8"), "text/csv")},
        params=params,
    )


def rows_of(response, action: str) -> list[dict]:
    return [row for row in response.json()["rows"] if row["action"] == action]


class TestDryRun:
    def test_a_clean_file_reports_what_it_would_create(self, admin_client, fixtures):
        body = HEADER + (
            "student,Nila,Suresh,nila@example.edu,S900,B.E. CSE,III,A\n"
            "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
        )
        response = upload(admin_client, body)

        assert response.status_code == 200
        body_json = response.json()
        assert body_json["dry_run"] is True
        assert body_json["created"] == 2
        assert body_json["errors"] == 0
        assert body_json["ok"] is True

    def test_a_dry_run_writes_nothing(self, admin_client, session: Session, fixtures):
        before = session.query(Account).count()
        upload(admin_client, HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n")

        assert session.query(Account).count() == before

    def test_it_reports_every_problem_at_once(self, admin_client, fixtures):
        """One failed upload per mistake is the thing this replaces."""
        body = HEADER + (
            "student,,Suresh,nila@example.edu,S900,B.E. CSE,III,A\n"
            "wizard,Ravi,Kumar,ravi@example.edu,F900,,,\n"
            "faculty,Meena,Iyer,not-an-email,F901,,,\n"
        )
        response = upload(admin_client, body)

        assert response.json()["errors"] == 3
        messages = " ".join(m for r in response.json()["rows"] for m in r["messages"])
        assert "First name is required" in messages
        assert "admin, faculty or student" in messages
        assert "not a valid email address" in messages


class TestFileShape:
    def test_a_byte_order_mark_does_not_break_the_headers(self, admin_client, fixtures):
        """Excel writes one, and it would otherwise become part of the first
        column's name."""
        body = "﻿" + HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
        response = admin_client.post(
            "/accounts/import",
            files={"file": ("roll.csv", body.encode("utf-8"), "text/csv")},
        )

        assert response.json()["errors"] == 0
        assert response.json()["created"] == 1

    def test_renamed_headings_are_recognised(self, admin_client, fixtures):
        body = (
            "Type,First Name,Surname,Email Address,Roll No,Programme,Year,Sec\n"
            "student,Nila,Suresh,nila@example.edu,S900,B.E. CSE,III,A\n"
        )
        response = upload(admin_client, body)

        assert response.json()["created"] == 1

    def test_missing_required_columns_is_a_file_level_error(self, admin_client, fixtures):
        response = upload(admin_client, "first_name,last_name\nNila,Suresh\n")

        assert response.json()["file_errors"]
        assert "role" in response.json()["file_errors"][0]
        assert response.json()["ok"] is False

    def test_blank_lines_are_ignored_rather_than_reported(self, admin_client, fixtures):
        body = HEADER + "\n\nfaculty,Ravi,Kumar,ravi@example.edu,F900,,,\n\n"
        response = upload(admin_client, body)

        assert response.json()["total"] == 1
        assert response.json()["errors"] == 0

    def test_a_header_with_no_rows_says_so(self, admin_client, fixtures):
        response = upload(admin_client, HEADER)

        assert "no data rows" in response.json()["file_errors"][0]


class TestDuplicates:
    def test_a_repeat_within_the_file_is_flagged_on_the_later_row(
        self, admin_client, fixtures
    ):
        body = HEADER + (
            "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
            "faculty,Ravi,Kumar,ravi@example.edu,F901,,,\n"
        )
        response = upload(admin_client, body)

        # The first occurrence still imports.
        assert response.json()["created"] == 1
        [bad] = rows_of(response, "error")
        assert bad["line"] == 3
        assert "Duplicate of line 2" in bad["messages"][0]

    def test_an_account_that_already_exists_is_skipped_by_default(
        self, admin_client, fixtures
    ):
        existing = fixtures["faculty"].email
        response = upload(
            admin_client, HEADER + f"faculty,Asha,Raman,{existing},F900,,,\n"
        )

        assert response.json()["skipped"] == 1
        assert response.json()["created"] == 0
        assert "left unchanged" in rows_of(response, "skip")[0]["messages"][0]

    def test_on_existing_update_moves_a_student_to_a_new_class(
        self, admin_client, session: Session, fixtures
    ):
        """Rolling a cohort up a year is the annual task this exists for."""
        student = fixtures["student"]
        other = admin_client.post(
            "/classes", json={"curriculum": "B.E. CSE", "level": "IV", "section": "A"}
        ).json()

        response = upload(
            admin_client,
            HEADER + f"student,Karthik,Iyer,{student.email},S2201,B.E. CSE,IV,A\n",
            dry_run="false",
            on_existing="update",
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 1

        session.refresh(student)
        assert student.class_group_id == other["id"]

    def test_a_taken_institutional_id_is_refused(self, admin_client, fixtures):
        taken = fixtures["faculty"].school_id
        response = upload(
            admin_client, HEADER + f"faculty,New,Person,new@example.edu,{taken},,,\n"
        )

        assert response.json()["errors"] == 1
        assert "already belongs" in rows_of(response, "error")[0]["messages"][0]


class TestStudentsNeedAClass:
    def test_a_student_without_class_columns_is_refused(self, admin_client, fixtures):
        response = upload(
            admin_client, HEADER + "student,Nila,Suresh,nila@example.edu,S900,,,\n"
        )

        assert response.json()["errors"] == 1
        assert "placed in a class" in rows_of(response, "error")[0]["messages"][0]

    def test_a_class_that_does_not_exist_is_named_in_the_message(
        self, admin_client, fixtures
    ):
        response = upload(
            admin_client,
            HEADER + "student,Nila,Suresh,nila@example.edu,S900,B.Tech IT,II,C\n",
        )

        message = rows_of(response, "error")[0]["messages"][0]
        assert "B.Tech IT" in message
        assert "Create it first" in message

    def test_class_matching_ignores_case_and_padding(self, admin_client, fixtures):
        response = upload(
            admin_client,
            HEADER + "student,Nila,Suresh,nila@example.edu,S900, b.e. cse , iii , a \n",
        )

        assert response.json()["created"] == 1


class TestWriting:
    def test_writing_requires_asking_for_it(
        self, admin_client, session: Session, fixtures
    ):
        body = HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
        response = upload(admin_client, body, dry_run="false")

        assert response.json()["dry_run"] is False
        assert session.query(Account).filter_by(email="ravi@example.edu").count() == 1

    def test_a_file_with_any_error_writes_nothing(
        self, admin_client, session: Session, fixtures
    ):
        """A partially imported roll is worse than none: the missing students
        are invisible until their response rates look wrong."""
        before = session.query(Account).count()
        body = HEADER + (
            "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
            "faculty,Broken,Row,not-an-email,F901,,,\n"
        )
        response = upload(admin_client, body, dry_run="false")

        assert response.status_code == 400
        assert "Nothing was imported" in response.json()["detail"]
        assert session.query(Account).count() == before

    def test_without_invitations_a_password_is_generated_and_works(
        self, admin_client, fixtures
    ):
        """The fallback for a college with no working outbound mail."""
        body = HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
        response = upload(admin_client, body, dry_run="false", invite="false")

        [row] = rows_of(response, "create")
        password = row["generated_password"]
        assert password and len(password) >= 12

        admin_client.post("/auth/logout")
        signed_in = admin_client.post(
            "/auth/login", json={"email": "ravi@example.edu", "password": password}
        )
        assert signed_in.status_code == 200

    def test_invitations_are_the_default_and_no_password_is_shown(
        self, admin_client, fixtures, outbox
    ):
        """A password nobody has to copy out of a browser is the point of
        having email at all."""
        body = HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
        response = upload(admin_client, body, dry_run="false")

        [row] = rows_of(response, "create")
        assert row["generated_password"] is None

        [message] = [m for m in outbox if m.to == "ravi@example.edu"]
        assert "/set-password?token=" in message.body

    def test_a_dry_run_sends_no_invitations(self, admin_client, fixtures, outbox):
        upload(admin_client, HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n")

        assert outbox == []

    def test_an_invited_account_can_set_a_password_and_sign_in(
        self, admin_client, fixtures, outbox
    ):
        upload(
            admin_client,
            HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n",
            dry_run="false",
        )
        [message] = [m for m in outbox if m.to == "ravi@example.edu"]
        token = message.body.split("/set-password?token=")[1].split()[0]

        admin_client.post("/auth/logout")
        confirmed = admin_client.post(
            "/auth/password-reset/confirm",
            params={"purpose": "invitation"},
            json={"token": token, "new_password": "a-password-i-chose"},
        )
        assert confirmed.status_code == 204

        signed_in = admin_client.post(
            "/auth/login",
            json={"email": "ravi@example.edu", "password": "a-password-i-chose"},
        )
        assert signed_in.status_code == 200

    def test_a_supplied_password_is_used_and_not_echoed(self, admin_client, fixtures):
        body = (
            "role,first_name,last_name,email,password\n"
            "faculty,Ravi,Kumar,ravi@example.edu,a-chosen-password\n"
        )
        response = upload(admin_client, body, dry_run="false")

        [row] = rows_of(response, "create")
        assert row["generated_password"] is None

        admin_client.post("/auth/logout")
        assert (
            admin_client.post(
                "/auth/login",
                json={"email": "ravi@example.edu", "password": "a-chosen-password"},
            ).status_code
            == 200
        )

    def test_imported_accounts_have_no_legacy_hash(
        self, admin_client, session: Session, fixtures
    ):
        upload(
            admin_client,
            HEADER + "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n",
            dry_run="false",
        )

        account = session.query(Account).filter_by(email="ravi@example.edu").one()
        assert account.password_hash.startswith("$argon2id$")
        assert account.legacy_md5 is None

    def test_emails_are_stored_lowercased(
        self, admin_client, session: Session, fixtures
    ):
        upload(
            admin_client,
            HEADER + "faculty,Ravi,Kumar,RAVI@Example.EDU,F900,,,\n",
            dry_run="false",
        )

        assert session.query(Account).filter_by(email="ravi@example.edu").count() == 1


class TestAccess:
    def test_a_student_cannot_import_accounts(self, student_client, fixtures):
        response = student_client.post(
            "/accounts/import",
            files={"file": ("roll.csv", HEADER.encode(), "text/csv")},
        )
        assert response.status_code == 403

    def test_an_anonymous_caller_cannot_import_accounts(self, client, fixtures):
        response = client.post(
            "/accounts/import",
            files={"file": ("roll.csv", HEADER.encode(), "text/csv")},
        )
        assert response.status_code == 401


class TestLineNumbers:
    def test_reported_lines_match_the_file_after_a_blank_row(
        self, admin_client, fixtures
    ):
        """An administrator fixing "line 4" must be looking at line 4. Counting
        yielded rows drifts, because blank rows are dropped before we see them."""
        body = HEADER + (
            "faculty,Ravi,Kumar,ravi@example.edu,F900,,,\n"
            "\n"
            "faculty,Broken,Row,not-an-email,F901,,,\n"
        )
        response = upload(admin_client, body)

        [bad] = rows_of(response, "error")
        assert bad["line"] == 4

    def test_a_quoted_field_spanning_lines_does_not_shift_later_numbers(
        self, admin_client, fixtures
    ):
        body = HEADER + (
            'faculty,"Ravi\nthe second",Kumar,ravi@example.edu,F900,,,\n'
            "faculty,Broken,Row,not-an-email,F901,,,\n"
        )
        response = upload(admin_client, body)

        [bad] = rows_of(response, "error")
        assert bad["line"] == 4

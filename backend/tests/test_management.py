"""Accounts and the teaching-assignment matrix."""

import hashlib

from app.models import Account, EvaluationResponse, EvaluationSubmission, Role

GOOD_PASSWORD = "a-sufficiently-long-password"


class TestAccounts:
    def _new_student(self, class_id: int, **overrides) -> dict:
        payload = {
            "role": "student",
            "first_name": "Nila",
            "last_name": "Suresh",
            "email": "nila.suresh@example.edu",
            "password": GOOD_PASSWORD,
            "school_id": "S9001",
            "class_group_id": class_id,
        }
        payload.update(overrides)
        return payload

    def test_creating_an_account_hashes_the_password(
        self, admin_client, session, fixtures
    ):
        response = admin_client.post(
            "/accounts", json=self._new_student(fixtures["class_group"].id)
        )
        assert response.status_code == 201, response.text

        account = session.get(Account, response.json()["id"])
        assert account.password_hash.startswith("$argon2id$")
        assert GOOD_PASSWORD not in account.password_hash

    def test_the_password_is_never_returned(self, admin_client, fixtures):
        body = admin_client.post(
            "/accounts", json=self._new_student(fixtures["class_group"].id)
        ).json()

        assert not {"password", "password_hash", "legacy_md5"} & set(body)

    def test_the_new_account_can_log_in(self, admin_client, fixtures):
        admin_client.post("/accounts", json=self._new_student(fixtures["class_group"].id))
        admin_client.post("/auth/logout")

        response = admin_client.post(
            "/auth/login",
            json={"email": "nila.suresh@example.edu", "password": GOOD_PASSWORD},
        )
        assert response.status_code == 200

    def test_emails_are_stored_lowercased(self, admin_client, session, fixtures):
        response = admin_client.post(
            "/accounts",
            json=self._new_student(
                fixtures["class_group"].id, email="MiXeD.CaSe@Example.EDU"
            ),
        )

        account = session.get(Account, response.json()["id"])
        assert account.email == "mixed.case@example.edu"

    def test_a_duplicate_email_is_409(self, admin_client, fixtures):
        admin_client.post("/accounts", json=self._new_student(fixtures["class_group"].id))

        clash = admin_client.post(
            "/accounts", json=self._new_student(fixtures["class_group"].id)
        )
        assert clash.status_code == 409

    def test_a_student_without_a_class_is_rejected(self, admin_client):
        response = admin_client.post(
            "/accounts",
            json={
                "role": "student",
                "first_name": "No",
                "last_name": "Class",
                "email": "noclass@example.edu",
                "password": GOOD_PASSWORD,
            },
        )
        assert response.status_code == 422

    def test_a_short_password_is_rejected(self, admin_client, fixtures):
        response = admin_client.post(
            "/accounts",
            json=self._new_student(fixtures["class_group"].id, password="short"),
        )
        assert response.status_code == 422

    def test_a_missing_class_is_404(self, admin_client):
        response = admin_client.post("/accounts", json=self._new_student(999999))
        assert response.status_code == 404

    def test_accounts_can_be_filtered_by_role(self, admin_client, fixtures):
        faculty = admin_client.get("/accounts", params={"role": "faculty"}).json()

        assert {row["role"] for row in faculty} == {"faculty"}
        assert fixtures["faculty"].id in [row["id"] for row in faculty]

    def test_accounts_can_be_filtered_by_class(self, admin_client, fixtures):
        listed = admin_client.get(
            "/accounts", params={"class_group_id": fixtures["class_group"].id}
        ).json()

        assert fixtures["student"].id in [row["id"] for row in listed]

    def test_the_role_cannot_be_changed_by_patch(self, admin_client, session, fixtures):
        """Role is absent from AccountUpdate on purpose; an unknown field is
        ignored rather than silently promoting a student."""
        student = fixtures["student"]

        admin_client.patch(f"/accounts/{student.id}", json={"role": "admin"})

        session.refresh(student)
        assert student.role is Role.student

    def test_setting_a_password_clears_a_migrated_hash(
        self, admin_client, session, fixtures
    ):
        student = fixtures["student"]
        student.legacy_md5 = hashlib.md5(b"old").hexdigest()
        session.commit()

        response = admin_client.patch(
            f"/accounts/{student.id}", json={"password": GOOD_PASSWORD}
        )
        assert response.status_code == 200

        session.refresh(student)
        assert student.legacy_md5 is None
        assert student.password_hash.startswith("$argon2id$")

    def test_an_admin_cannot_delete_their_own_account(self, admin_client, admin_account):
        response = admin_client.delete(f"/accounts/{admin_account.id}")

        assert response.status_code == 409
        assert "signed in" in response.json()["detail"]

    def test_the_last_administrator_cannot_be_deleted(
        self, admin_client, session, admin_account
    ):
        """Deleting it would leave nobody able to administer the system."""
        other = Account(
            role=Role.admin,
            first_name="Second",
            last_name="Admin",
            email="second.admin@example.edu",
            password_hash="placeholder",
        )
        session.add(other)
        session.commit()

        assert admin_client.delete(f"/accounts/{other.id}").status_code == 204
        # admin_account is now the only one left, and is also the caller.
        assert admin_client.delete(f"/accounts/{admin_account.id}").status_code == 409

    def test_the_last_administrator_cannot_be_deactivated(
        self, admin_client, admin_account
    ):
        response = admin_client.patch(
            f"/accounts/{admin_account.id}", json={"is_active": False}
        )

        assert response.status_code == 409
        assert "only active administrator" in response.json()["detail"]

    def test_an_account_with_evaluations_cannot_be_deleted(
        self, admin_client, session, fixtures
    ):
        session.add(
            EvaluationSubmission(
                term_id=fixtures["term"].id,
                student_id=fixtures["student"].id,
                assignment_id=fixtures["assignment"].id,
            )
        )
        session.commit()

        response = admin_client.delete(f"/accounts/{fixtures['faculty'].id}")
        assert response.status_code == 409
        assert "Deactivate" in response.json()["detail"]

    def test_a_student_cannot_reach_the_accounts_api(self, student_client):
        assert student_client.get("/accounts").status_code == 403


class TestAssignmentMatrix:
    def _item(self, fixtures) -> dict:
        return {
            "faculty_id": fixtures["faculty"].id,
            "class_group_id": fixtures["class_group"].id,
            "subject_id": fixtures["subject"].id,
        }

    def _url(self, fixtures) -> str:
        return f"/academic-years/{fixtures['term'].id}/assignments"

    def test_the_existing_matrix_is_listed_with_labels(self, admin_client, fixtures):
        response = admin_client.get(self._url(fixtures))

        assert response.status_code == 200
        [row] = response.json()
        assert row["faculty_name"] == "Asha Raman"
        assert row["subject_code"] == "CS3401"
        assert row["class_label"] == "B.E. CSE III-A"

    def test_replacing_with_the_same_set_is_a_no_op(
        self, admin_client, session, fixtures
    ):
        original_id = fixtures["assignment"].id

        response = admin_client.put(
            self._url(fixtures), json={"assignments": [self._item(fixtures)]}
        )

        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == [original_id]

    def test_a_new_assignment_is_added(self, admin_client, fixtures):
        second_subject = admin_client.post(
            "/subjects", json={"code": "CS3402", "name": "Databases"}
        ).json()
        addition = {**self._item(fixtures), "subject_id": second_subject["id"]}

        response = admin_client.put(
            self._url(fixtures), json={"assignments": [self._item(fixtures), addition]}
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_an_omitted_assignment_is_removed(self, admin_client, fixtures):
        response = admin_client.put(self._url(fixtures), json={"assignments": []})

        assert response.status_code == 200
        assert response.json() == []

    def test_an_evaluated_assignment_cannot_be_removed(
        self, admin_client, session, fixtures
    ):
        """The legacy save_restriction deleted unconditionally. With the
        foreign key now cascading, that would take the feedback with it."""
        session.add(
            EvaluationSubmission(
                term_id=fixtures["term"].id,
                student_id=fixtures["student"].id,
                assignment_id=fixtures["assignment"].id,
            )
        )
        session.add(
            EvaluationResponse(
                term_id=fixtures["term"].id, assignment_id=fixtures["assignment"].id
            )
        )
        session.commit()

        response = admin_client.put(self._url(fixtures), json={"assignments": []})

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "already have submitted evaluations" in detail
        assert "Asha Raman" in detail and "CS3401" in detail

    def test_a_refused_removal_leaves_the_data_intact(
        self, admin_client, session, fixtures
    ):
        session.add(
            EvaluationSubmission(
                term_id=fixtures["term"].id,
                student_id=fixtures["student"].id,
                assignment_id=fixtures["assignment"].id,
            )
        )
        session.commit()

        admin_client.put(self._url(fixtures), json={"assignments": []})

        session.expire_all()
        assert session.query(EvaluationSubmission).count() == 1
        assert admin_client.get(self._url(fixtures)).json() != []

    def test_a_non_faculty_account_is_rejected(self, admin_client, fixtures):
        response = admin_client.put(
            self._url(fixtures),
            json={
                "assignments": [
                    {**self._item(fixtures), "faculty_id": fixtures["student"].id}
                ]
            },
        )

        assert response.status_code == 400
        assert "Not a faculty account" in response.json()["detail"]

    def test_an_unknown_subject_is_rejected(self, admin_client, fixtures):
        response = admin_client.put(
            self._url(fixtures),
            json={"assignments": [{**self._item(fixtures), "subject_id": 999999}]},
        )

        assert response.status_code == 400
        assert "No such subject" in response.json()["detail"]

    def test_an_unknown_class_is_rejected(self, admin_client, fixtures):
        response = admin_client.put(
            self._url(fixtures),
            json={"assignments": [{**self._item(fixtures), "class_group_id": 999999}]},
        )

        assert response.status_code == 400
        assert "No such class" in response.json()["detail"]

    def test_a_repeated_assignment_is_rejected(self, admin_client, fixtures):
        response = admin_client.put(
            self._url(fixtures),
            json={"assignments": [self._item(fixtures), self._item(fixtures)]},
        )

        assert response.status_code == 422

    def test_an_unknown_term_is_404(self, admin_client):
        response = admin_client.put(
            "/academic-years/999999/assignments", json={"assignments": []}
        )
        assert response.status_code == 404

    def test_a_student_cannot_edit_the_matrix(self, student_client, fixtures):
        response = student_client.put(self._url(fixtures), json={"assignments": []})
        assert response.status_code == 403

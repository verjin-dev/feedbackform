"""CRUD behaviour for terms, classes, subjects, criteria and questions."""

import pytest

from app.models import AcademicTerm, Criterion, TermStatus


class TestCrudShape:
    """The five reference resources share one implementation, so the common
    behaviour is checked once across all of them rather than five times."""

    CASES = [
        ("/classes", {"curriculum": "B.E. ECE", "level": "II", "section": "B"}),
        ("/subjects", {"code": "EC2401", "name": "Signals"}),
        ("/academic-years", {"year": "2027-2028", "semester": 2}),
        ("/criteria", {"name": "Punctuality"}),
    ]

    @pytest.mark.parametrize("path,payload", CASES)
    def test_create_then_read_back(self, admin_client, path, payload):
        created = admin_client.post(path, json=payload)
        assert created.status_code == 201, created.text
        new_id = created.json()["id"]

        fetched = admin_client.get(f"{path}/{new_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == new_id

    @pytest.mark.parametrize("path,payload", CASES)
    def test_it_appears_in_the_list(self, admin_client, path, payload):
        new_id = admin_client.post(path, json=payload).json()["id"]

        listed = admin_client.get(path).json()
        assert new_id in [row["id"] for row in listed]

    @pytest.mark.parametrize("path,payload", CASES)
    def test_missing_records_are_404_not_500(self, admin_client, path, payload):
        assert admin_client.get(f"{path}/999999").status_code == 404

    @pytest.mark.parametrize("path,payload", CASES)
    def test_a_student_is_refused(self, student_client, path, payload):
        assert student_client.get(path).status_code == 403
        assert student_client.post(path, json=payload).status_code == 403

    @pytest.mark.parametrize("path,payload", CASES)
    def test_an_anonymous_caller_is_refused(self, client, path, payload):
        assert client.get(path).status_code == 401


class TestDuplicates:
    def test_a_duplicate_subject_code_is_409(self, admin_client):
        payload = {"code": "CS9999", "name": "First"}
        assert admin_client.post("/subjects", json=payload).status_code == 201

        clash = admin_client.post("/subjects", json={"code": "CS9999", "name": "Second"})
        assert clash.status_code == 409
        assert "already" in clash.json()["detail"].lower()

    def test_a_duplicate_class_is_409(self, admin_client, fixtures):
        existing = fixtures["class_group"]
        clash = admin_client.post(
            "/classes",
            json={
                "curriculum": existing.curriculum,
                "level": existing.level,
                "section": existing.section,
            },
        )
        assert clash.status_code == 409

    def test_a_duplicate_term_is_409(self, admin_client, fixtures):
        clash = admin_client.post(
            "/academic-years", json={"year": "2025-2026", "semester": 1}
        )
        assert clash.status_code == 409


class TestDeletionSafety:
    def test_a_class_in_use_cannot_be_deleted(self, admin_client, fixtures):
        """A student and an assignment both reference it."""
        response = admin_client.delete(f"/classes/{fixtures['class_group'].id}")

        assert response.status_code == 409
        assert "reference" in response.json()["detail"].lower()

    def test_a_subject_in_use_cannot_be_deleted(self, admin_client, fixtures):
        assert admin_client.delete(f"/subjects/{fixtures['subject'].id}").status_code == 409

    def test_a_criterion_with_questions_cannot_be_deleted(self, admin_client, fixtures):
        assert (
            admin_client.delete(f"/criteria/{fixtures['criterion'].id}").status_code == 409
        )

    def test_an_unused_subject_can_be_deleted(self, admin_client):
        new_id = admin_client.post(
            "/subjects", json={"code": "TMP101", "name": "Temporary"}
        ).json()["id"]

        assert admin_client.delete(f"/subjects/{new_id}").status_code == 204
        assert admin_client.get(f"/subjects/{new_id}").status_code == 404

    def test_the_current_term_cannot_be_deleted(self, admin_client, fixtures):
        response = admin_client.delete(f"/academic-years/{fixtures['term'].id}")

        assert response.status_code == 409
        assert "current" in response.json()["detail"].lower()


class TestActivation:
    def test_activating_a_term_makes_it_current(self, admin_client, session, fixtures):
        new_id = admin_client.post(
            "/academic-years", json={"year": "2026-2027", "semester": 1}
        ).json()["id"]

        response = admin_client.post(f"/academic-years/{new_id}/activate")
        assert response.status_code == 200
        assert response.json()["is_current"] is True

    def test_activating_clears_the_previous_current_term(
        self, admin_client, session, fixtures
    ):
        """make_default did this in a separate statement with nothing
        guaranteeing exactly one row won."""
        previous = fixtures["term"]
        new_id = admin_client.post(
            "/academic-years", json={"year": "2026-2027", "semester": 1}
        ).json()["id"]

        admin_client.post(f"/academic-years/{new_id}/activate")

        session.expire_all()
        current = [t.id for t in session.query(AcademicTerm).filter_by(is_current=True)]
        assert current == [new_id]
        assert session.get(AcademicTerm, previous.id).is_current is False

    def test_activating_the_already_current_term_is_harmless(
        self, admin_client, session, fixtures
    ):
        response = admin_client.post(f"/academic-years/{fixtures['term'].id}/activate")

        assert response.status_code == 200
        session.expire_all()
        assert session.query(AcademicTerm).filter_by(is_current=True).count() == 1

    def test_activating_a_missing_term_is_404(self, admin_client):
        assert admin_client.post("/academic-years/999999/activate").status_code == 404


class TestReordering:
    @pytest.fixture
    def criteria_ids(self, admin_client, fixtures) -> list[int]:
        ids = [fixtures["criterion"].id]
        for name in ("Communication", "Fairness"):
            ids.append(admin_client.post("/criteria", json={"name": name}).json()["id"])
        return ids

    def test_new_items_go_to_the_end(self, admin_client, criteria_ids):
        listed = admin_client.get("/criteria").json()
        assert [row["id"] for row in listed] == criteria_ids
        assert [row["position"] for row in listed] == [1, 2, 3]

    def test_reordering_rewrites_every_position(self, admin_client, criteria_ids):
        reversed_ids = list(reversed(criteria_ids))

        response = admin_client.put("/criteria/order", json={"ids": reversed_ids})
        assert response.status_code == 204

        listed = admin_client.get("/criteria").json()
        assert [row["id"] for row in listed] == reversed_ids
        assert [row["position"] for row in listed] == [1, 2, 3]

    def test_a_partial_ordering_is_refused(self, admin_client, criteria_ids):
        """Accepting a subset would let a stale client silently drop items."""
        response = admin_client.put("/criteria/order", json={"ids": criteria_ids[:2]})

        assert response.status_code == 400
        assert "every item" in response.json()["detail"]

    def test_an_unknown_id_is_refused(self, admin_client, criteria_ids):
        response = admin_client.put(
            "/criteria/order", json={"ids": [*criteria_ids, 999999]}
        )

        assert response.status_code == 400
        assert "999999" in response.json()["detail"]

    def test_duplicate_ids_are_refused(self, admin_client, criteria_ids):
        response = admin_client.put(
            "/criteria/order", json={"ids": [criteria_ids[0]] * len(criteria_ids)}
        )

        assert response.status_code == 422

    def test_a_failed_reorder_changes_nothing(self, admin_client, criteria_ids, session):
        admin_client.put("/criteria/order", json={"ids": criteria_ids[:2]})

        session.expire_all()
        positions = {c.id: c.position for c in session.query(Criterion)}
        assert positions == dict(zip(criteria_ids, [1, 2, 3], strict=True))


class TestQuestions:
    def test_questions_can_be_filtered_by_term(self, admin_client, fixtures):
        listed = admin_client.get(
            "/questions", params={"term_id": fixtures["term"].id}
        ).json()

        assert len(listed) == len(fixtures["questions"])
        assert {row["term_id"] for row in listed} == {fixtures["term"].id}

    def test_creating_a_question_against_a_missing_term_is_404(
        self, admin_client, fixtures
    ):
        response = admin_client.post(
            "/questions",
            json={
                "term_id": 999999,
                "criterion_id": fixtures["criterion"].id,
                "text": "Orphan question",
            },
        )
        assert response.status_code == 404

    def test_creating_a_question_against_a_missing_criterion_is_404(
        self, admin_client, fixtures
    ):
        response = admin_client.post(
            "/questions",
            json={
                "term_id": fixtures["term"].id,
                "criterion_id": 999999,
                "text": "Orphan question",
            },
        )
        assert response.status_code == 404

    def test_question_ordering_is_scoped_to_one_term(self, admin_client, session, fixtures):
        """Two terms each have their own questionnaire; reordering one must not
        require naming the other's questions."""
        other_term = admin_client.post(
            "/academic-years", json={"year": "2026-2027", "semester": 2}
        ).json()
        admin_client.post(
            "/questions",
            json={
                "term_id": other_term["id"],
                "criterion_id": fixtures["criterion"].id,
                "text": "A question in another term",
            },
        )

        ids = [q.id for q in fixtures["questions"]]
        response = admin_client.put(
            "/questions/order",
            params={"term_id": fixtures["term"].id},
            json={"ids": list(reversed(ids))},
        )
        assert response.status_code == 204

    def test_status_transitions_are_constrained_to_the_enum(self, admin_client, fixtures):
        response = admin_client.patch(
            f"/academic-years/{fixtures['term'].id}", json={"status": "whenever"}
        )
        assert response.status_code == 422

    def test_a_valid_status_change_is_accepted(self, admin_client, fixtures):
        response = admin_client.patch(
            f"/academic-years/{fixtures['term'].id}",
            json={"status": TermStatus.closed.value},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "closed"

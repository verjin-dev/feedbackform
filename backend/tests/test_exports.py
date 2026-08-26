"""Accreditation exports.

The thing an assessor is handed. Two properties matter more than the rest: the
numbers must match the screen they were checked against, and a withheld
average must stay withheld — a mean printed for three responses in the one
document nobody re-checks is the worst place for it to appear.
"""

import csv
import io

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Account,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Role,
)
from app.services.reporting import build_faculty_report


def read(response) -> list[dict]:
    return list(csv.DictReader(io.StringIO(response.text.lstrip("﻿"))))


def _student(session, fixtures, n):
    account = Account(
        role=Role.student,
        first_name=f"Student{n}",
        last_name="Extra",
        email=f"student{n}@example.edu",
        password_hash="placeholder",
        class_group_id=fixtures["class_group"].id,
    )
    session.add(account)
    session.commit()
    return account


def record(session, fixtures, ratings, student):
    session.add(
        EvaluationSubmission(
            term_id=fixtures["term"].id,
            student_id=student.id,
            assignment_id=fixtures["assignment"].id,
        )
    )
    response = EvaluationResponse(
        term_id=fixtures["term"].id, assignment_id=fixtures["assignment"].id
    )
    session.add(response)
    session.flush()
    for question, rating in zip(fixtures["questions"], ratings, strict=True):
        session.add(
            EvaluationRating(
                response_id=response.id, question_id=question.id, rating=rating
            )
        )
    session.commit()


@pytest.fixture
def answered(session: Session, fixtures: dict) -> dict:
    """Six responses — enough for a mean to be published."""
    students = [fixtures["student"]] + [_student(session, fixtures, n) for n in range(1, 6)]
    for index, student in enumerate(students):
        record(session, fixtures, [5, 4] if index % 2 == 0 else [4, 3], student)
    return fixtures


class TestQuestionnaire:
    def test_it_exports_the_questions_actually_asked(self, admin_client, fixtures):
        rows = read(admin_client.get("/exports/questionnaire.csv"))

        assert [row["question"] for row in rows] == [
            q.text for q in fixtures["questions"]
        ]
        assert rows[0]["criterion"] == "Subject knowledge"

    def test_the_filename_is_dated(self, admin_client, fixtures):
        disposition = admin_client.get("/exports/questionnaire.csv").headers[
            "content-disposition"
        ]

        assert "attachment" in disposition
        assert "2025-2026" in disposition
        assert disposition.endswith('.csv"')


class TestParticipation:
    def test_it_reports_the_denominator(self, admin_client, answered):
        [row] = read(admin_client.get("/exports/participation.csv"))

        assert row["students_eligible"] == "6"
        assert row["responses"] == "6"
        assert row["response_rate_percent"] == "100.0"
        assert row["faculty"] == "Asha Raman"

    def test_an_unanswered_assignment_shows_a_zero_rate_not_a_blank(
        self, admin_client, fixtures
    ):
        [row] = read(admin_client.get("/exports/participation.csv"))

        assert row["responses"] == "0"
        assert row["response_rate_percent"] == "0.0"
        assert row["reliability"] == "insufficient"
        assert "no average published" in row["note"]


class TestResults:
    def test_it_carries_the_raw_counts(self, admin_client, answered):
        """A mean can be recomputed from these, so nobody is asked to trust an
        arithmetic step they cannot see."""
        rows = read(admin_client.get("/exports/results.csv"))

        first = rows[0]
        counted = sum(int(first[f"rated_{n}"]) for n in range(1, 6))
        assert counted == int(first["responses"]) == 6

    def test_a_published_mean_matches_the_screen(self, admin_client, session, answered):
        """The export and the report must not be two implementations of the
        same arithmetic."""
        rows = read(admin_client.get("/exports/results.csv"))
        on_screen = build_faculty_report(session, answered["faculty"], answered["term"])
        expected = on_screen["assignments"][0]["criteria"][0]["questions"][0]["mean"]

        assert float(rows[0]["mean"]) == expected

    def test_a_withheld_mean_is_blank_and_never_zero(self, admin_client, session, fixtures):
        """Zero in a spreadsheet reads as a unanimous worst score."""
        record(session, fixtures, [5, 5], fixtures["student"])
        record(session, fixtures, [4, 4], _student(session, fixtures, 1))

        rows = read(admin_client.get("/exports/results.csv"))
        assert rows[0]["responses"] == "2"
        assert rows[0]["mean"] == ""
        assert rows[0]["mean_low"] == ""
        assert "Fewer than 5 responses" in rows[0]["note"]

    def test_every_question_appears_even_when_unanswered(self, admin_client, fixtures):
        rows = read(admin_client.get("/exports/results.csv"))

        assert len(rows) == len(fixtures["questions"])
        assert all(row["responses"] == "0" for row in rows)

    def test_it_can_be_filtered_by_curriculum(self, admin_client, answered):
        matching = read(
            admin_client.get("/exports/results.csv", params={"curriculum": "B.E. CSE"})
        )
        other = read(
            admin_client.get("/exports/results.csv", params={"curriculum": "B.E. ECE"})
        )

        assert len(matching) == 2
        assert other == []

    def test_the_filter_ignores_case(self, admin_client, answered):
        rows = read(
            admin_client.get("/exports/results.csv", params={"curriculum": "b.e. cse"})
        )
        assert len(rows) == 2

    def test_a_filtered_filename_names_the_curriculum(self, admin_client, answered):
        disposition = admin_client.get(
            "/exports/results.csv", params={"curriculum": "B.E. CSE"}
        ).headers["content-disposition"]

        assert "BE-CSE" in disposition


class TestSummary:
    def test_it_describes_the_return(self, admin_client, answered):
        body = admin_client.get("/exports/summary").json()

        assert body["term"]["label"] == "2025-2026 semester 1"
        assert body["questions"] == 2
        assert body["criteria"] == 1
        assert body["assignments"] == 1
        assert body["faculty"] == 1
        assert body["students_eligible"] == 6
        assert body["responses"] == 6
        assert body["response_rate"] == 1.0
        assert body["generated_at"]

    def test_it_says_how_many_assignments_are_below_the_threshold(
        self, admin_client, session, fixtures
    ):
        """The number an assessor should be told, rather than left to infer
        from blank cells."""
        record(session, fixtures, [5, 5], fixtures["student"])

        body = admin_client.get("/exports/summary").json()
        assert body["assignments_below_threshold"] == 1
        assert body["assignments_with_published_means"] == 0
        assert body["minimum_responses_for_mean"] == 5

    def test_curricula_are_listed_for_filtering(self, admin_client, fixtures):
        assert admin_client.get("/exports/curricula").json() == ["B.E. CSE"]


class TestAccess:
    def test_faculty_cannot_export(self, client, session, fixtures):
        from app.core.security import hash_password

        faculty = fixtures["faculty"]
        faculty.password_hash = hash_password("faculty-password")
        session.commit()
        client.post(
            "/auth/login", json={"email": faculty.email, "password": "faculty-password"}
        )

        assert client.get("/exports/results.csv").status_code == 403

    def test_students_cannot_export(self, student_client, fixtures):
        assert student_client.get("/exports/results.csv").status_code == 403

    def test_an_anonymous_caller_cannot_export(self, client, fixtures):
        assert client.get("/exports/results.csv").status_code == 401

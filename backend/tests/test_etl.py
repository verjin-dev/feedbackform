"""The legacy import, exercised against a database shaped like the real one.

The fixture deliberately contains what four years of an unconstrained schema
accumulates: a duplicate submission, a rating out of range, a student whose
class was deleted, an orphaned assignment, and the same email in two account
tables. Every one of those is something the new schema refuses.
"""

import hashlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Question,
    Role,
    TeachingAssignment,
    TermStatus,
)
from etl.import_legacy import BLOCKER, analyse, run_import
from etl.legacy import LegacyReader

MD5 = hashlib.md5(b"admin123").hexdigest()

LEGACY_SCHEMA = """
CREATE TABLE academic_list (id INTEGER PRIMARY KEY, year TEXT, semester INTEGER,
    is_default INTEGER DEFAULT 0, status INTEGER DEFAULT 0);
CREATE TABLE class_list (id INTEGER PRIMARY KEY, curriculum TEXT, level TEXT, section TEXT);
CREATE TABLE subject_list (id INTEGER PRIMARY KEY, code TEXT, subject TEXT, description TEXT);
CREATE TABLE criteria_list (id INTEGER PRIMARY KEY, criteria TEXT, order_by INTEGER);
CREATE TABLE question_list (id INTEGER PRIMARY KEY, academic_id INTEGER, question TEXT,
    order_by INTEGER, criteria_id INTEGER);
CREATE TABLE users (id INTEGER PRIMARY KEY, firstname TEXT, lastname TEXT, email TEXT,
    password TEXT, avatar TEXT, date_created TEXT);
CREATE TABLE faculty_list (id INTEGER PRIMARY KEY, school_id TEXT, firstname TEXT,
    lastname TEXT, email TEXT, password TEXT, avatar TEXT, date_created TEXT);
CREATE TABLE student_list (id INTEGER PRIMARY KEY, school_id TEXT, firstname TEXT,
    lastname TEXT, email TEXT, password TEXT, class_id INTEGER, avatar TEXT,
    date_created TEXT);
CREATE TABLE restriction_list (id INTEGER PRIMARY KEY, academic_id INTEGER,
    faculty_id INTEGER, class_id INTEGER, subject_id INTEGER);
CREATE TABLE evaluation_list (evaluation_id INTEGER PRIMARY KEY, academic_id INTEGER,
    class_id INTEGER, student_id INTEGER, subject_id INTEGER, faculty_id INTEGER,
    restriction_id INTEGER, date_taken TEXT);
CREATE TABLE evaluation_answers (evaluation_id INTEGER, question_id INTEGER, rate INTEGER);
"""

SEED = f"""
INSERT INTO academic_list VALUES (1, '2024-2025', 1, 0, 2), (2, '2025-2026', 1, 1, 1);
INSERT INTO class_list VALUES (1, 'B.E. CSE', 'III', 'A'), (2, 'B.E. ECE', 'II', 'B');
INSERT INTO subject_list VALUES (1, 'CS3401', 'Algorithms', ''), (2, 'EC2201', 'Circuits', '');
INSERT INTO criteria_list VALUES (1, 'Subject knowledge', 2), (2, 'Communication', 1);
INSERT INTO question_list VALUES
    (1, 2, 'Explains concepts clearly.', 2, 1),
    (2, 2, 'Answers questions thoroughly.', 1, 1),
    (3, 2, 'Speaks audibly.', 1, 2);
INSERT INTO users VALUES (1, 'Priya', 'Menon', 'admin@example.edu', '{MD5}', '', '');
INSERT INTO faculty_list VALUES
    (1, 'F1001', 'Asha', 'Raman', 'asha@example.edu', '{MD5}', '', ''),
    (2, 'F1002', 'Meera', 'Nair', 'meera@example.edu', '{MD5}', '', '');
INSERT INTO student_list VALUES
    (1, 'S001', 'Karthik', 'Iyer', 'karthik@example.edu', '{MD5}', 1, '', ''),
    (2, 'S002', 'Divya', 'Rao', 'divya@example.edu', '{MD5}', 1, '', ''),
    (3, 'S003', 'Ghost', 'Student', 'ghost@example.edu', '{MD5}', 99, '', '');
INSERT INTO restriction_list VALUES
    (1, 2, 1, 1, 1),
    (2, 2, 2, 1, 2),
    (3, 2, 99, 1, 1);
INSERT INTO evaluation_list VALUES
    (1, 2, 1, 1, 1, 1, 1, ''),
    (2, 2, 1, 1, 1, 1, 1, ''),
    (3, 2, 1, 2, 1, 1, 1, '');
INSERT INTO evaluation_answers VALUES
    (1, 1, 5), (1, 2, 4), (1, 3, 5),
    (2, 1, 1), (2, 2, 1), (2, 3, 1),
    (3, 1, 3), (3, 2, 3), (3, 3, 3);
"""


@pytest.fixture
def legacy(tmp_path) -> LegacyReader:
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        for statement in LEGACY_SCHEMA.strip().split(";"):
            if statement.strip():
                connection.execute(text(statement))
        for statement in SEED.strip().split(";"):
            if statement.strip():
                connection.execute(text(statement))
    engine.dispose()

    reader = LegacyReader(f"sqlite:///{path}")
    yield reader
    reader.close()


def codes(findings) -> set[str]:
    return {finding.code for finding in findings}


class TestAnalysis:
    def test_it_writes_nothing(self, legacy, session: Session):
        analyse(legacy)
        assert session.query(Account).count() == 0

    def test_a_student_whose_class_was_deleted_is_a_blocker(self, legacy):
        findings = analyse(legacy)
        assert "student-without-class" in codes(findings)

    def test_duplicate_submissions_are_reported(self, legacy):
        """Nothing in the legacy schema prevented these."""
        findings = analyse(legacy)
        [finding] = [f for f in findings if f.code == "duplicate-submission"]
        assert finding.rows == [2]

    def test_orphaned_assignments_are_reported(self, legacy):
        findings = analyse(legacy)
        [finding] = [f for f in findings if f.code == "orphan-assignment"]
        assert finding.rows == [3]

    def test_a_shared_email_across_account_tables_is_a_blocker(self, legacy):
        with legacy.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE faculty_list SET email = 'admin@example.edu' WHERE id = 1"
                )
            )
        findings = analyse(legacy)
        blocker = [f for f in findings if f.code == "duplicate-email"]
        assert blocker and blocker[0].level == BLOCKER

    def test_a_rating_outside_the_legend_is_a_blocker(self, legacy):
        with legacy.engine.begin() as connection:
            connection.execute(text("UPDATE evaluation_answers SET rate = 9 WHERE rowid = 1"))
        findings = analyse(legacy)
        blocker = [f for f in findings if f.code == "rating-out-of-range"]
        assert blocker and blocker[0].level == BLOCKER

    def test_the_anonymity_loss_is_stated_plainly(self, legacy):
        """It is one-way, so it should never be a surprise."""
        [note] = [f for f in analyse(legacy) if f.code == "anonymity"]
        assert "one-way" in note.message


class TestImport:
    def test_reference_data_transfers(self, legacy, session: Session):
        run_import(legacy, session, seed=1)

        assert session.query(AcademicTerm).count() == 2
        assert session.query(Question).count() == 3

    def test_only_one_term_becomes_current(self, legacy, session: Session):
        run_import(legacy, session, seed=1)

        current = session.query(AcademicTerm).filter_by(is_current=True).all()
        assert [term.year for term in current] == ['2025-2026']

    def test_status_integers_become_the_enum(self, legacy, session: Session):
        run_import(legacy, session, seed=1)

        by_year = {term.year: term.status for term in session.query(AcademicTerm)}
        assert by_year['2024-2025'] is TermStatus.closed
        assert by_year['2025-2026'] is TermStatus.open

    def test_the_three_account_tables_become_one(self, legacy, session: Session):
        run_import(legacy, session, seed=1)

        roles = {
            role: session.query(Account).filter_by(role=role).count() for role in Role
        }
        assert roles[Role.admin] == 1
        assert roles[Role.faculty] == 2
        # The student whose class was deleted is skipped, not imported broken.
        assert roles[Role.student] == 2

    def test_passwords_arrive_as_legacy_hashes_awaiting_upgrade(self, legacy, session: Session):
        run_import(legacy, session, seed=1)

        account = session.query(Account).filter_by(email='asha@example.edu').one()
        assert account.legacy_md5 == MD5
        assert account.password_hash is None
        assert account.needs_password_upgrade is True

    def test_emails_are_lowercased(self, legacy, session: Session):
        with legacy.engine.begin() as connection:
            connection.execute(text("UPDATE faculty_list SET email='ASHA@Example.EDU' WHERE id=1"))
        run_import(legacy, session, seed=1)

        assert session.query(Account).filter_by(email='asha@example.edu').count() == 1

    def test_orphaned_assignments_are_skipped(self, legacy, session: Session):
        summary = run_import(legacy, session, seed=1)

        assert session.query(TeachingAssignment).count() == 2
        assert summary.skipped['assignment (orphaned)'] == 1

    def test_the_duplicate_submission_is_dropped(self, legacy, session: Session):
        summary = run_import(legacy, session, seed=1)

        # Three evaluation_list rows, one of them a repeat by the same student.
        assert session.query(EvaluationSubmission).count() == 2
        assert summary.skipped['evaluation (duplicate)'] == 1

    def test_submissions_and_responses_stay_in_step(self, legacy, session: Session):
        """Response rates depend on this equality, and nothing else links the
        two halves together."""
        run_import(legacy, session, seed=1)

        assert (
            session.query(EvaluationSubmission).count()
            == session.query(EvaluationResponse).count()
            == 2
        )
        assert session.query(EvaluationRating).count() == 6

    def test_no_rating_can_be_traced_to_a_student(self, legacy, session: Session):
        run_import(legacy, session, seed=1)

        columns = {c.name for c in EvaluationResponse.__table__.columns}
        assert 'student_id' not in columns
        for response in session.query(EvaluationResponse):
            assert not hasattr(response, 'student_id')

    def test_criteria_and_questions_are_renumbered_from_one(self, legacy, session: Session):
        """Legacy stored order in a text column and sorted with abs(order_by)."""
        run_import(legacy, session, seed=1)

        positions = sorted(q.position for q in session.query(Question))
        assert positions == [1, 2, 3]

    def test_importing_twice_is_refused_rather_than_silently_doubling(
        self, legacy, session: Session
    ):
        from sqlalchemy.exc import IntegrityError

        run_import(legacy, session, seed=1)
        with pytest.raises(IntegrityError):
            run_import(legacy, session, seed=1)


class TestReconciliation:
    def test_it_reports_agreement_after_a_clean_import(self, legacy, session: Session):
        from etl.reconcile import reconcile

        run_import(legacy, session, seed=1)
        ok, bad = reconcile(legacy, session)

        assert bad == [], bad
        assert any('per-question means compared' in line for line in ok)

    def test_it_catches_a_report_that_moved(self, legacy, session: Session):
        """The check that matters: if a mean changed, say so."""
        from etl.reconcile import reconcile

        run_import(legacy, session, seed=1)
        # Corrupt one imported rating so the aggregates disagree.
        rating = session.query(EvaluationRating).first()
        rating.rating = 1 if rating.rating != 1 else 5
        session.commit()

        _ok, bad = reconcile(legacy, session)
        assert any('question mean moved' in line for line in bad), bad

    def test_it_catches_submissions_and_responses_drifting_apart(
        self, legacy, session: Session
    ):
        from etl.reconcile import reconcile

        run_import(legacy, session, seed=1)
        session.delete(session.query(EvaluationResponse).first())
        session.commit()

        _ok, bad = reconcile(legacy, session)
        assert any('submissions vs responses' in line for line in bad), bad

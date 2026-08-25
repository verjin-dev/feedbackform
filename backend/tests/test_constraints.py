"""Each test here covers a defect the legacy schema actually allowed."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Role,
    TermStatus,
)


def _submit(session: Session, fixtures: dict, ratings: list[int]) -> None:
    """Write both halves of a submission the way the API will: one
    transaction, two unconnected rows."""
    term, assignment = fixtures["term"], fixtures["assignment"]

    session.add(
        EvaluationSubmission(
            term_id=term.id,
            student_id=fixtures["student"].id,
            assignment_id=assignment.id,
        )
    )
    response = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
    session.add(response)
    session.flush()
    for question, rating in zip(fixtures["questions"], ratings, strict=True):
        session.add(
            EvaluationRating(
                response_id=response.id, question_id=question.id, rating=rating
            )
        )
    session.commit()


def test_a_student_cannot_submit_twice(session: Session, fixtures: dict):
    """The legacy app relied on the UI hiding already-rated assignments, so a
    repeated POST wrote a second evaluation and skewed the percentages."""
    _submit(session, fixtures, [5, 4])
    session.rollback()

    with pytest.raises(IntegrityError):
        _submit(session, fixtures, [1, 1])


def test_rating_must_be_within_the_legend(session: Session, fixtures: dict):
    """The form offers 1-5; nothing in the legacy schema enforced it."""
    term, assignment = fixtures["term"], fixtures["assignment"]
    response = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
    session.add(response)
    session.flush()

    session.add(
        EvaluationRating(
            response_id=response.id, question_id=fixtures["questions"][0].id, rating=9
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_one_answer_per_question_per_response(session: Session, fixtures: dict):
    """evaluation_answers had no primary key at all."""
    term, assignment = fixtures["term"], fixtures["assignment"]
    response = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
    session.add(response)
    session.flush()

    question = fixtures["questions"][0]
    session.add_all(
        [
            EvaluationRating(response_id=response.id, question_id=question.id, rating=5),
            EvaluationRating(response_id=response.id, question_id=question.id, rating=1),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_student_must_belong_to_a_class(session: Session):
    """Legacy student_list.class_id was a plain int with no constraint, so a
    student could exist with class_id = 0 and see no assignments."""
    session.add(
        Account(
            role=Role.student,
            first_name="Unplaced",
            last_name="Student",
            email="unplaced@example.edu",
            password_hash="argon2-placeholder",
            class_group_id=None,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_faculty_need_no_class(session: Session):
    """The same constraint must not accidentally require a class for staff."""
    session.add(
        Account(
            role=Role.faculty,
            first_name="Meera",
            last_name="Nair",
            email="meera.nair@example.edu",
            password_hash="argon2-placeholder",
        )
    )
    session.commit()


def test_an_account_must_have_some_credential(session: Session):
    session.add(
        Account(
            role=Role.admin,
            first_name="No",
            last_name="Credential",
            email="nocred@example.edu",
            password_hash=None,
            legacy_md5=None,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_migrated_account_may_hold_only_a_legacy_hash(session: Session):
    """Accounts arrive from the PHP database with md5 and no Argon2 hash until
    their first login."""
    session.add(
        Account(
            role=Role.admin,
            first_name="Migrated",
            last_name="Admin",
            email="migrated@example.edu",
            password_hash=None,
            legacy_md5="0192023a7bbd73250516f069df18b500",
        )
    )
    session.commit()

    account = session.query(Account).filter_by(email="migrated@example.edu").one()
    assert account.needs_password_upgrade is True


def test_only_one_term_can_be_current(session: Session, fixtures: dict):
    """make_default cleared the previous default in a separate statement, with
    nothing preventing two rows from winning."""
    session.add(
        AcademicTerm(
            year="2026-2027", semester=1, status=TermStatus.pending, is_current=True
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_several_terms_may_be_non_current(session: Session, fixtures: dict):
    """The partial index must only constrain the true values."""
    session.add_all(
        [
            AcademicTerm(year="2024-2025", semester=1, is_current=False),
            AcademicTerm(year="2024-2025", semester=2, is_current=False),
        ]
    )
    session.commit()


def test_an_assignment_cannot_be_duplicated(session: Session, fixtures: dict):
    from app.models import TeachingAssignment

    session.add(
        TeachingAssignment(
            term_id=fixtures["term"].id,
            faculty_id=fixtures["faculty"].id,
            class_group_id=fixtures["class_group"].id,
            subject_id=fixtures["subject"].id,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_response_count_matches_submission_count(session: Session, fixtures: dict):
    """The two halves are unlinked, so this equality is the only integrity
    check available — and it is what response-rate reporting depends on."""
    _submit(session, fixtures, [5, 4])

    submissions = session.query(EvaluationSubmission).count()
    responses = session.query(EvaluationResponse).count()
    assert submissions == responses == 1
    assert session.query(EvaluationRating).count() == 2

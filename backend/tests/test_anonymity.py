"""Structural guarantees for the anonymity split.

These assert the *shape* of the schema rather than behaviour, on purpose. The
legacy design failure was a column existing where it should not have, and a
future change that reintroduces one would otherwise pass every behavioural
test. If one of these fails, read the note at the top of app/models/evaluation.py
before changing the assertion.

Note that the guarantee is currently partial: response ids are UUIDv7 and so
disclose their creation time. The last two tests document that exposure rather
than assert it away.
"""

import time
import uuid

from app.core.identifiers import uuid7_timestamp_ms
from app.models import EvaluationRating, EvaluationResponse, EvaluationSubmission


def test_response_has_no_student_reference():
    columns = {c.name for c in EvaluationResponse.__table__.columns}
    assert "student_id" not in columns
    assert "submission_id" not in columns

    referenced_tables = {
        fk.column.table.name for fk in EvaluationResponse.__table__.foreign_keys
    }
    assert "account" not in referenced_tables
    assert "evaluation_submission" not in referenced_tables


def test_response_has_no_timestamp():
    """A timestamp here could be matched against submission.submitted_at to
    re-link a response to the student who gave it."""
    columns = {c.name for c in EvaluationResponse.__table__.columns}
    assert not (columns & {"created_at", "updated_at", "submitted_at"})


def test_response_ids_are_uuid7(session, fixtures):
    term, assignment = fixtures["term"], fixtures["assignment"]
    first = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
    session.add(first)
    session.commit()

    assert isinstance(first.id, uuid.UUID)
    assert first.id.version == 7


def test_response_ids_disclose_their_creation_time(session, fixtures):
    """Documents the accepted limitation rather than asserting a guarantee.

    UUIDv7 is time-ordered, so a response id reveals when it was written to
    within a few milliseconds. That is enough to match it against
    evaluation_submission.submitted_at and identify the student.

    This test exists so the exposure is visible in the suite instead of being
    an unremarked property of the id format. If the anonymity guarantee is
    later required to hold against database access, this test should start
    failing — change the id generator, don't delete the test.
    """
    term, assignment = fixtures["term"], fixtures["assignment"]
    before_ms = int(time.time() * 1000)
    response = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
    session.add(response)
    session.commit()
    after_ms = int(time.time() * 1000)

    recovered = uuid7_timestamp_ms(response.id)
    assert before_ms <= recovered <= after_ms


def test_response_ids_are_still_ordered_by_creation(session, fixtures):
    """The other half of the same limitation: ordering alone re-links rows to
    sequential submission ids, with no timestamp needed."""
    term, assignment = fixtures["term"], fixtures["assignment"]
    ids = []
    for _ in range(3):
        response = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
        session.add(response)
        session.commit()
        ids.append(response.id)
        time.sleep(0.002)

    assert ids == sorted(ids)


def test_ratings_reach_no_further_than_the_response():
    referenced_tables = {
        fk.column.table.name for fk in EvaluationRating.__table__.foreign_keys
    }
    assert referenced_tables == {"evaluation_response", "question"}
    assert "account" not in referenced_tables


def test_submission_holds_no_answers():
    """The other half of the split: participation is recorded, opinions are not."""
    columns = {c.name for c in EvaluationSubmission.__table__.columns}
    assert "rating" not in columns
    assert "question_id" not in columns
    assert "response_id" not in columns

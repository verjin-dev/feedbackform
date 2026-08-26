"""Context for a score, and the lines it must not cross.

"Is 4.2 good?" has no answer on its own, and the only comparison available
without context is against other people. These tests exist to keep the answer
to that question from becoming an answer to "who is worst?".
"""

import pytest

from app.core.security import hash_password
from app.models import (
    Account,
    ClassGroup,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Question,
    Role,
    Subject,
    TeachingAssignment,
)
from app.services.cohort import MIN_COHORT, bands_for
from app.services.reporting import assignment_reports

PASSWORD = "cohort-password-here"


def peer(
    session,
    fixtures,
    n: int,
    rating: int,
    *,
    curriculum: str = "B.E. CSE",
    responses: int = 6,
):
    """Another instructor teaching another subject.

    Six responses by default, which clears the publish threshold; pass fewer
    to build a peer whose mean is withheld.
    """
    group = session.query(ClassGroup).filter_by(curriculum=curriculum).first()
    if group is None:
        group = ClassGroup(curriculum=curriculum, level="III", section="A")
        session.add(group)
        session.flush()

    subject = Subject(code=f"XX{n:03d}", name=f"Subject {n}")
    instructor = Account(
        role=Role.faculty,
        first_name=f"Peer{n}",
        last_name="Instructor",
        email=f"peer{n}@example.edu",
        password_hash="placeholder",
    )
    session.add_all([subject, instructor])
    session.flush()

    assignment = TeachingAssignment(
        term_id=fixtures["term"].id,
        faculty_id=instructor.id,
        class_group_id=group.id,
        subject_id=subject.id,
    )
    session.add(assignment)
    session.flush()

    question = session.query(Question).filter_by(term_id=fixtures["term"].id).first()
    for s in range(responses):
        learner = Account(
            role=Role.student,
            first_name=f"P{n}S{s}",
            last_name="X",
            email=f"p{n}s{s}@example.edu",
            password_hash="x",
            class_group_id=group.id,
        )
        session.add(learner)
        session.flush()
        session.add(
            EvaluationSubmission(
                term_id=fixtures["term"].id,
                student_id=learner.id,
                assignment_id=assignment.id,
            )
        )
        response = EvaluationResponse(
            term_id=fixtures["term"].id, assignment_id=assignment.id
        )
        session.add(response)
        session.flush()
        session.add(
            EvaluationRating(
                response_id=response.id, question_id=question.id, rating=rating
            )
        )
    session.commit()
    return assignment


def rate_own(session, fixtures, rating: int, count: int = 6):
    question = session.query(Question).filter_by(term_id=fixtures["term"].id).first()
    for s in range(count):
        learner = Account(
            role=Role.student,
            first_name=f"Own{s}",
            last_name="X",
            email=f"own{s}@example.edu",
            password_hash="x",
            class_group_id=fixtures["class_group"].id,
        )
        session.add(learner)
        session.flush()
        session.add(
            EvaluationSubmission(
                term_id=fixtures["term"].id,
                student_id=learner.id,
                assignment_id=fixtures["assignment"].id,
            )
        )
        response = EvaluationResponse(
            term_id=fixtures["term"].id, assignment_id=fixtures["assignment"].id
        )
        session.add(response)
        session.flush()
        session.add(
            EvaluationRating(
                response_id=response.id, question_id=question.id, rating=rating
            )
        )
    session.commit()


@pytest.fixture
def faculty_client(client, session, fixtures):
    faculty = fixtures["faculty"]
    faculty.password_hash = hash_password(PASSWORD)
    session.commit()
    client.post("/auth/login", json={"email": faculty.email, "password": PASSWORD})
    return client


@pytest.fixture
def cohort_of_six(session, fixtures):
    """Six peers scoring 2, 3, 3, 4, 5, 5 — and the viewer at 4."""
    for index, rating in enumerate([2, 3, 3, 4, 5, 5]):
        peer(session, fixtures, index, rating)
    rate_own(session, fixtures, 4)
    return fixtures


class TestTheBand:
    def test_it_reports_a_range_and_a_middle(self, session, cohort_of_six, fixtures):
        reports = assignment_reports(session, fixtures["term"], faculty_id=fixtures["faculty"].id)
        [band] = [b for b in bands_for(session, fixtures["term"], reports).values()]

        assert band is not None
        assert band["p25"] <= band["median"] <= band["p75"]
        assert band["size"] == 6

    def test_the_viewer_is_excluded_from_their_own_comparison(
        self, session, cohort_of_six, fixtures
    ):
        """Comparing a score against a band it is part of flatters it."""
        reports = assignment_reports(session, fixtures["term"], faculty_id=fixtures["faculty"].id)
        [band] = list(bands_for(session, fixtures["term"], reports).values())

        # Six peers, not seven entries.
        assert band["size"] == 6

    def test_the_basis_says_what_the_comparison_is(
        self, session, cohort_of_six, fixtures
    ):
        reports = assignment_reports(session, fixtures["term"], faculty_id=fixtures["faculty"].id)
        [band] = list(bands_for(session, fixtures["term"], reports).values())

        assert "B.E. CSE" in band["basis"]
        assert "2025-2026" in band["basis"]

    def test_unpublished_means_do_not_move_the_band(self, session, fixtures):
        """A mean drawn from two responses is not a comparison point, and
        including it would let the band be moved by a figure the system
        refuses to show."""
        for index, rating in enumerate([4, 4, 4, 4, 4]):
            peer(session, fixtures, index, rating)
        # A sixth peer, rating 1, but with too few responses to publish.
        peer(session, fixtures, 99, 1, responses=2)
        rate_own(session, fixtures, 4)

        reports = assignment_reports(session, fixtures["term"], faculty_id=fixtures["faculty"].id)
        [band] = list(bands_for(session, fixtures["term"], reports).values())

        # Only the five publishable peers, all at 4.0.
        assert band["size"] == 5
        assert band["median"] == 4.0


class TestDisclosureLimits:
    def test_no_band_below_the_minimum_cohort(self, session, fixtures):
        """With two instructors in a department, a median tells the first
        exactly what the second scored."""
        for index, rating in enumerate([3, 5]):
            peer(session, fixtures, index, rating)
        rate_own(session, fixtures, 4)

        reports = assignment_reports(session, fixtures["term"], faculty_id=fixtures["faculty"].id)
        assert list(bands_for(session, fixtures["term"], reports).values()) == [None]

    def test_the_minimum_is_five_others(self, session, fixtures):
        assert MIN_COHORT == 5

        for index, rating in enumerate([4] * (MIN_COHORT - 1)):
            peer(session, fixtures, index, rating)
        rate_own(session, fixtures, 4)

        reports = assignment_reports(session, fixtures["term"], faculty_id=fixtures["faculty"].id)
        assert list(bands_for(session, fixtures["term"], reports).values()) == [None]

    def test_a_different_curriculum_is_not_a_peer(self, session, fixtures):
        """The comparison group is the same curriculum, so a full cohort in
        another one does not unlock a band here."""
        for index, rating in enumerate([3, 4, 4, 5, 5, 5]):
            peer(session, fixtures, index, rating, curriculum="B.E. ECE")
        rate_own(session, fixtures, 4)

        reports = assignment_reports(session, fixtures["term"], faculty_id=fixtures["faculty"].id)
        assert list(bands_for(session, fixtures["term"], reports).values()) == [None]


class TestNeverARanking:
    def test_the_band_names_nobody(self, faculty_client, cohort_of_six, fixtures):
        body = faculty_client.get("/reports/me").json()
        band = body["assignments"][0]["cohort"]

        assert set(band) == {"size", "p25", "median", "p75", "basis"}

    def test_no_peer_identity_reaches_the_client(
        self, faculty_client, cohort_of_six, session
    ):
        """The whole payload, not just the band: a name leaking anywhere in the
        response turns context into a comparison against a person."""
        raw = faculty_client.get("/reports/me").text

        for instructor in session.query(Account).filter_by(role=Role.faculty):
            if instructor.email == "asha.raman@example.edu":
                continue
            assert instructor.last_name not in raw or instructor.first_name not in raw
            assert instructor.email not in raw

    def test_no_position_or_percentile_is_reported(
        self, faculty_client, cohort_of_six
    ):
        """A percentile is a ranking with one row visible."""
        raw = faculty_client.get("/reports/me").text.lower()

        assert "percentile" not in raw
        assert "rank" not in raw
        assert "position" not in raw

    def test_there_is_no_endpoint_listing_faculty_by_score(self, admin_client):
        """The most requested feature, and the one that does the most damage."""
        paths = admin_client.get("/openapi.json").json()["paths"]

        assert not any(
            "leaderboard" in path or "ranking" in path or "league" in path
            for path in paths
        )


class TestThroughTheApi:
    def test_an_assignment_carries_its_band(self, faculty_client, cohort_of_six):
        assignment = faculty_client.get("/reports/me").json()["assignments"][0]

        assert assignment["cohort"] is not None
        assert assignment["cohort"]["size"] == 6

    def test_a_thin_cohort_returns_null_rather_than_an_empty_band(
        self, faculty_client, session, fixtures
    ):
        rate_own(session, fixtures, 4)

        assignment = faculty_client.get("/reports/me").json()["assignments"][0]
        assert assignment["cohort"] is None

    def test_an_admin_sees_the_same_band(self, admin_client, cohort_of_six, fixtures):
        assignment = admin_client.get(
            f"/reports/faculty/{fixtures['faculty'].id}"
        ).json()["assignments"][0]

        assert assignment["cohort"]["size"] == 6

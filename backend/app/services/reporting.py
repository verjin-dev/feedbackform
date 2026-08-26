"""Aggregation for the faculty and response-rate reports.

Kept out of the route layer so the arithmetic can be tested directly, and
because this is the part of the legacy application most worth reimplementing
deliberately rather than transcribing. `get_report` divided each rating tally
by an unchecked count and omitted questions nobody had answered, so a barely
answered questionnaire rendered as a complete one.

Three rules hold throughout:

  - A denominator of zero yields None, never 0.0 and never an exception.
  - Every question in the term appears in the output, with explicit zero
    counts when unanswered.
  - Percentages are of the responses to *that question*, so they sum to 100
    within a question regardless of how many people skipped others.
"""

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    Criterion,
    EvaluationResponse,
    EvaluationRating,
    Question,
    Role,
    TeachingAssignment,
)

RATINGS = (1, 2, 3, 4, 5)

# Below this many responses no mean is published at all.
#
# A mean of seven self-selected opinions, printed to two decimal places beside
# one drawn from twenty-eight, claims a precision it does not have. The count
# is shown instead. Five is a judgement rather than a statistical threshold:
# low enough to keep small electives usable, high enough that one strong
# opinion cannot carry the figure.
MIN_RESPONSES_FOR_MEAN = 5

# Above the threshold but below this share of the class, the mean is published
# and flagged: it is real, but it is a minority speaking.
LOW_RESPONSE_RATE = 0.30

INSUFFICIENT = "insufficient"
LOW = "low"
ADEQUATE = "adequate"


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _mean_from_counts(counts: dict[int, int]) -> float | None:
    total = sum(counts.values())
    if total == 0:
        return None
    weighted = sum(rating * count for rating, count in counts.items())
    return round(weighted / total, 3)


def _interval_from_counts(counts: dict[int, int]) -> tuple[float, float] | None:
    """A 95% interval for the mean, clamped to the 1-5 scale.

    Reported alongside the mean so the width of the estimate is visible. With
    six responses the interval is wide enough to make the point on its own,
    which is the reason for showing it rather than a bare number.
    """
    total = sum(counts.values())
    mean = _mean_from_counts(counts)
    if mean is None or total < 2:
        return None

    variance = sum(count * (rating - mean) ** 2 for rating, count in counts.items()) / (
        total - 1
    )
    standard_error = (variance / total) ** 0.5
    margin = 1.96 * standard_error
    return (
        round(max(1.0, mean - margin), 2),
        round(min(5.0, mean + margin), 2),
    )


def _reliability(responses: int, response_rate: float | None) -> str:
    if responses < MIN_RESPONSES_FOR_MEAN:
        return INSUFFICIENT
    if response_rate is not None and response_rate < LOW_RESPONSE_RATE:
        return LOW
    return ADEQUATE


def _mean_of(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _eligible_student_counts(db: Session, class_ids: set[int]) -> dict[int, int]:
    """How many students could have answered, per class.

    This is the denominator for the response rate, and it is a live count: a
    student added late raises the denominator for everyone in that class.
    """
    if not class_ids:
        return {}
    rows = db.execute(
        select(Account.class_group_id, func.count())
        .where(
            Account.role == Role.student,
            Account.is_active.is_(True),
            Account.class_group_id.in_(class_ids),
        )
        .group_by(Account.class_group_id)
    ).all()
    return {class_id: count for class_id, count in rows}


def _response_counts(db: Session, assignment_ids: set[int]) -> dict[int, int]:
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(EvaluationResponse.assignment_id, func.count())
        .where(EvaluationResponse.assignment_id.in_(assignment_ids))
        .group_by(EvaluationResponse.assignment_id)
    ).all()
    return {assignment_id: count for assignment_id, count in rows}


def _rating_counts(
    db: Session, assignment_ids: set[int]
) -> dict[int, dict[int, dict[int, int]]]:
    """assignment -> question -> rating -> count, in one query."""
    if not assignment_ids:
        return {}

    rows = db.execute(
        select(
            EvaluationResponse.assignment_id,
            EvaluationRating.question_id,
            EvaluationRating.rating,
            func.count(),
        )
        .join(EvaluationRating, EvaluationRating.response_id == EvaluationResponse.id)
        .where(EvaluationResponse.assignment_id.in_(assignment_ids))
        .group_by(
            EvaluationResponse.assignment_id,
            EvaluationRating.question_id,
            EvaluationRating.rating,
        )
    ).all()

    tally: dict[int, dict[int, dict[int, int]]] = defaultdict(
        lambda: defaultdict(lambda: dict.fromkeys(RATINGS, 0))
    )
    for assignment_id, question_id, rating, count in rows:
        tally[assignment_id][question_id][rating] = count
    return tally


def term_questionnaire(db: Session, term_id: int) -> list[tuple[Criterion, list[Question]]]:
    """Criteria and their questions, in display order.

    Drives the report structure, which is why unanswered questions still
    appear: the shape comes from the questionnaire, not from the answers.
    """
    questions = db.scalars(
        select(Question)
        .where(Question.term_id == term_id)
        .order_by(Question.position, Question.id)
    ).unique().all()

    grouped: dict[int, list[Question]] = defaultdict(list)
    for question in questions:
        grouped[question.criterion_id].append(question)

    criteria = db.scalars(
        select(Criterion)
        .where(Criterion.id.in_(grouped))
        .order_by(Criterion.position, Criterion.id)
    ).unique().all()

    return [(criterion, grouped[criterion.id]) for criterion in criteria]


def _build_question_report(question: Question, counts: dict[int, int]) -> dict:
    responses = sum(counts.values())
    publishable = responses >= MIN_RESPONSES_FOR_MEAN

    return {
        "question_id": question.id,
        "text": question.text,
        "counts": {str(rating): counts.get(rating, 0) for rating in RATINGS},
        "percentages": {
            str(rating): (
                round(counts.get(rating, 0) / responses * 100, 2) if responses else 0.0
            )
            for rating in RATINGS
        },
        "responses": responses,
        # Withheld below the threshold rather than printed imprecisely. The
        # distribution is still returned: a reader can see the shape of four
        # answers without being handed a figure that looks authoritative.
        "mean": _mean_from_counts(counts) if publishable else None,
        "mean_range": _interval_from_counts(counts) if publishable else None,
        "reliability": _reliability(responses, None),
    }


def assignment_reports(
    db: Session,
    term: AcademicTerm,
    *,
    faculty_id: int | None = None,
    curriculum: str | None = None,
) -> list[dict]:
    """Every assignment in the term, aggregated once.

    The faculty report, the admin report and the accreditation export all read
    this. Two implementations of the same arithmetic would eventually disagree,
    and a document submitted to an accreditor that does not match the screen it
    was checked against is the worst version of that problem.
    """
    statement = select(TeachingAssignment).where(TeachingAssignment.term_id == term.id)
    if faculty_id is not None:
        statement = statement.where(TeachingAssignment.faculty_id == faculty_id)
    assignments = db.scalars(statement.order_by(TeachingAssignment.id)).unique().all()

    if curriculum is not None:
        # There is no department entity in the schema; curriculum on the class
        # is the closest thing to one, so that is what this filters on.
        wanted = curriculum.strip().lower()
        assignments = [
            a for a in assignments if a.class_group.curriculum.strip().lower() == wanted
        ]

    assignment_ids = {a.id for a in assignments}
    class_ids = {a.class_group_id for a in assignments}

    eligible = _eligible_student_counts(db, class_ids)
    responses = _response_counts(db, assignment_ids)
    tally = _rating_counts(db, assignment_ids)
    questionnaire = term_questionnaire(db, term.id)

    reports = []
    for assignment in assignments:
        per_question = tally.get(assignment.id, {})

        criteria_reports = []
        for criterion, questions in questionnaire:
            question_reports = [
                _build_question_report(
                    question, per_question.get(question.id, dict.fromkeys(RATINGS, 0))
                )
                for question in questions
            ]
            criteria_reports.append(
                {
                    "criterion_id": criterion.id,
                    "name": criterion.name,
                    "questions": question_reports,
                    "mean": _mean_of(
                        [q["mean"] for q in question_reports if q["mean"] is not None]
                    ),
                }
            )

        answered = responses.get(assignment.id, 0)
        eligible_here = eligible.get(assignment.class_group_id, 0)
        rate = _safe_ratio(answered, eligible_here)
        publishable = answered >= MIN_RESPONSES_FOR_MEAN

        reports.append(
            {
                "assignment_id": assignment.id,
                "faculty_id": assignment.faculty_id,
                "faculty_name": assignment.faculty.full_name,
                "subject_id": assignment.subject_id,
                "subject_code": assignment.subject.code,
                "subject_name": assignment.subject.name,
                "class_group_id": assignment.class_group_id,
                "class_label": assignment.class_group.label,
                "curriculum": assignment.class_group.curriculum,
                "eligible_students": eligible_here,
                "responses": answered,
                "response_rate": rate,
                "reliability": _reliability(answered, rate),
                "criteria": criteria_reports,
                "mean": (
                    _mean_of([c["mean"] for c in criteria_reports if c["mean"] is not None])
                    if publishable
                    else None
                ),
            }
        )
    return reports


def build_faculty_report(db: Session, faculty: Account, term: AcademicTerm) -> dict:
    reports = assignment_reports(db, term, faculty_id=faculty.id)
    return {
        "faculty_id": faculty.id,
        "faculty_name": faculty.full_name,
        "term": term,
        "assignments": reports,
        "mean": _mean_of([a["mean"] for a in reports if a["mean"] is not None]),
    }


def build_response_rate_report(db: Session, term: AcademicTerm) -> dict:
    assignments = db.scalars(
        select(TeachingAssignment)
        .where(TeachingAssignment.term_id == term.id)
        .order_by(TeachingAssignment.id)
    ).unique().all()

    eligible = _eligible_student_counts(db, {a.class_group_id for a in assignments})
    responses = _response_counts(db, {a.id for a in assignments})

    rows = []
    total_eligible = 0
    total_responses = 0
    for assignment in assignments:
        eligible_here = eligible.get(assignment.class_group_id, 0)
        answered = responses.get(assignment.id, 0)
        total_eligible += eligible_here
        total_responses += answered

        rows.append(
            {
                "assignment_id": assignment.id,
                "faculty_id": assignment.faculty_id,
                "faculty_name": assignment.faculty.full_name,
                "subject_code": assignment.subject.code,
                "class_label": assignment.class_group.label,
                "eligible_students": eligible_here,
                "responses": answered,
                "response_rate": _safe_ratio(answered, eligible_here),
            }
        )

    return {
        "term": term,
        "rows": rows,
        "eligible_students": total_eligible,
        "responses": total_responses,
        "response_rate": _safe_ratio(total_responses, total_eligible),
    }

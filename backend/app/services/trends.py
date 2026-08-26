"""The same instructor, term after term.

Feedback that cannot be compared to last time is a verdict. Feedback that can
is a direction, and a direction is the thing people are willing to look at.
The data has been keyed correctly since the migration; nothing read it until
now.

What can honestly be trended is decided by the schema. Criteria are global
rows that persist across terms, so a criterion mean in 2024 and one in 2025
refer to the same thing. Questions are recreated per term, so the "same"
question in two terms is two rows, and joining them would mean matching on
text — which silently breaks the series the first time somebody fixes a typo.
Question-level trends are therefore not offered rather than offered and wrong.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicTerm, Account, TeachingAssignment
from app.services.reporting import (
    MIN_RESPONSES_FOR_MEAN,
    _mean_of,
    _reliability,
    _safe_ratio,
    assignment_reports,
)

# Enough to see a direction without turning the page into a history lesson.
DEFAULT_TERM_LIMIT = 6


def _terms_taught(db: Session, faculty_id: int, limit: int) -> list[AcademicTerm]:
    """Terms this person actually taught in, oldest first.

    Terms they did not teach are left out rather than plotted as a gap: a
    sabbatical is not a drop in rating, and a line through zero would read as
    one.
    """
    terms = db.scalars(
        select(AcademicTerm)
        .join(TeachingAssignment, TeachingAssignment.term_id == AcademicTerm.id)
        .where(TeachingAssignment.faculty_id == faculty_id)
        .distinct()
    ).all()

    # year is text ("2025-2026"), which sorts correctly for that format.
    ordered = sorted(terms, key=lambda term: (term.year, term.semester))
    return ordered[-limit:]


def _point(term: AcademicTerm, mean: float | None, responses: int, eligible: int) -> dict:
    rate = _safe_ratio(responses, eligible)
    return {
        "term_id": term.id,
        "label": f"{term.year} S{term.semester}",
        "mean": mean,
        "responses": responses,
        "eligible_students": eligible,
        "response_rate": rate,
        "reliability": _reliability(responses, rate),
    }


def faculty_trend(
    db: Session, faculty: Account, *, limit: int = DEFAULT_TERM_LIMIT
) -> dict:
    terms = _terms_taught(db, faculty.id, limit)

    overall: list[dict] = []
    by_criterion: dict[int, dict] = {}
    by_subject: dict[int, dict] = {}

    for term in terms:
        reports = assignment_reports(db, term, faculty_id=faculty.id)

        responses = sum(r["responses"] for r in reports)
        eligible = sum(r["eligible_students"] for r in reports)
        # Suppressed on the same rule as everywhere else. A trend point drawn
        # from three responses would put a dot on a chart that the eye reads as
        # a fact.
        term_mean = (
            _mean_of([r["mean"] for r in reports if r["mean"] is not None])
            if responses >= MIN_RESPONSES_FOR_MEAN
            else None
        )
        overall.append(_point(term, term_mean, responses, eligible))

        # --- per criterion ---
        criterion_values: dict[int, tuple[str, list[float]]] = {}
        for report in reports:
            for criterion in report["criteria"]:
                name, values = criterion_values.setdefault(
                    criterion["criterion_id"], (criterion["name"], [])
                )
                if criterion["mean"] is not None:
                    values.append(criterion["mean"])

        for criterion_id, (name, values) in criterion_values.items():
            series = by_criterion.setdefault(
                criterion_id, {"criterion_id": criterion_id, "name": name, "points": []}
            )
            series["points"].append(
                _point(
                    term,
                    _mean_of(values) if responses >= MIN_RESPONSES_FOR_MEAN else None,
                    responses,
                    eligible,
                )
            )

        # --- per subject ---
        for report in reports:
            series = by_subject.setdefault(
                report["subject_id"],
                {
                    "subject_id": report["subject_id"],
                    "code": report["subject_code"],
                    "name": report["subject_name"],
                    "points": [],
                },
            )
            series["points"].append(
                _point(
                    term,
                    report["mean"],
                    report["responses"],
                    report["eligible_students"],
                )
            )

    return {
        "faculty_id": faculty.id,
        "faculty_name": faculty.full_name,
        "terms": [
            {
                "id": term.id,
                "year": term.year,
                "semester": term.semester,
                "label": f"{term.year} S{term.semester}",
            }
            for term in terms
        ],
        "overall": overall,
        # Sorted so the chart order does not shuffle between requests.
        "criteria": sorted(by_criterion.values(), key=lambda s: s["name"]),
        "subjects": sorted(by_subject.values(), key=lambda s: s["code"]),
        "minimum_responses_for_mean": MIN_RESPONSES_FOR_MEAN,
    }

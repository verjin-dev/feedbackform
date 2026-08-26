"""Files for an accreditation return.

Indian engineering programmes have to evidence student feedback for NBA and
NAAC, and until now the evidence was screenshots. What an assessor wants is
narrow and specific: the instrument that was actually used, how many people
answered out of how many could have, and the results — with enough detail that
the numbers can be checked rather than taken on trust.

Every figure comes from app.services.reporting, so an export and the screen it
was checked against cannot disagree. That includes withholding averages below
the response threshold: an export that quietly printed a mean for three
responses would undo the honesty the reports were built for, in the one
document where it matters most.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AcademicTerm, ClassGroup
from app.services.reporting import (
    LOW_RESPONSE_RATE,
    MIN_RESPONSES_FOR_MEAN,
    RATINGS,
    _safe_ratio,
    assignment_reports,
    questionnaire_for,
    term_questionnaire,
)

settings = get_settings()

RELIABILITY_NOTE = {
    "insufficient": f"Fewer than {MIN_RESPONSES_FOR_MEAN} responses; no average published",
    "low": f"Under {int(LOW_RESPONSE_RATE * 100)}% of the class responded",
    "adequate": "",
}


def term_label(term: AcademicTerm) -> str:
    return f"{term.year} semester {term.semester}"


def file_stem(term: AcademicTerm, kind: str, curriculum: str | None) -> str:
    parts = ["evaluation", kind, term.year.replace(" ", ""), f"sem{term.semester}"]
    if curriculum:
        parts.append(curriculum.replace(" ", "-").replace(".", ""))
    parts.append(datetime.now(UTC).strftime("%Y-%m-%d"))
    return "-".join(parts)


def _write(rows: list[dict], columns: list[str]) -> str:
    buffer = io.StringIO()
    # Excel is the thing that opens these; a BOM keeps it from mangling any
    # non-ASCII in a name or subject title.
    buffer.write("﻿")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def curricula(db: Session) -> list[str]:
    """What can be filtered on. Named for what it is: the schema has no
    department entity, and curriculum is the closest thing to one."""
    return sorted(
        {
            value.strip()
            for (value,) in db.execute(select(ClassGroup.curriculum)).all()
            if value and value.strip()
        }
    )


# --- The instrument --------------------------------------------------------

QUESTIONNAIRE_COLUMNS = [
    "criterion_order",
    "criterion",
    "question_order",
    "question",
    "who_answers",
]


def questionnaire_csv(
    db: Session, term: AcademicTerm, curriculum: str | None = None
) -> str:
    """The questions actually asked, in the order they were asked.

    An assessor checking that feedback was collected against a stated
    instrument needs the instrument, not a description of it.

    Since questions became department-scoped, a flat list is no longer the
    whole instrument: a reader could not tell that one department never saw a
    question, and would read its absence from the results as non-response.
    `who_answers` names the population for each row. Filtered to a department,
    the file is that department's instrument and nothing else.
    """
    questionnaire = (
        questionnaire_for(db, term.id, curriculum)
        if curriculum is not None
        else term_questionnaire(db, term.id)
    )

    rows = []
    for criterion_index, (criterion, questions) in enumerate(questionnaire, start=1):
        for question_index, question in enumerate(questions, start=1):
            rows.append(
                {
                    "criterion_order": criterion_index,
                    "criterion": criterion.name,
                    "question_order": question_index,
                    "question": question.text,
                    "who_answers": question.curriculum or "All departments",
                }
            )
    return _write(rows, QUESTIONNAIRE_COLUMNS)


# --- Participation ---------------------------------------------------------

PARTICIPATION_COLUMNS = [
    "curriculum",
    "class",
    "subject_code",
    "subject",
    "faculty",
    "students_eligible",
    "responses",
    "response_rate_percent",
    "reliability",
    "note",
]


def participation_csv(
    db: Session, term: AcademicTerm, curriculum: str | None = None
) -> str:
    rows = []
    for report in assignment_reports(db, term, curriculum=curriculum):
        rate = report["response_rate"]
        rows.append(
            {
                "curriculum": report["curriculum"],
                "class": report["class_label"],
                "subject_code": report["subject_code"],
                "subject": report["subject_name"],
                "faculty": report["faculty_name"],
                "students_eligible": report["eligible_students"],
                "responses": report["responses"],
                "response_rate_percent": "" if rate is None else round(rate * 100, 1),
                "reliability": report["reliability"],
                "note": RELIABILITY_NOTE[report["reliability"]],
            }
        )
    return _write(rows, PARTICIPATION_COLUMNS)


# --- Results ---------------------------------------------------------------

RESULTS_COLUMNS = [
    "curriculum",
    "class",
    "subject_code",
    "subject",
    "faculty",
    "criterion",
    "question",
    "responses",
    *[f"rated_{rating}" for rating in RATINGS],
    "mean",
    "mean_low",
    "mean_high",
    "reliability",
    "note",
]


def results_csv(db: Session, term: AcademicTerm, curriculum: str | None = None) -> str:
    """One row per question per assignment, with the raw counts.

    The counts are the point: a mean can be recomputed from them, so an
    assessor is not asked to trust an arithmetic step they cannot see.
    """
    rows = []
    for report in assignment_reports(db, term, curriculum=curriculum):
        for criterion in report["criteria"]:
            for question in criterion["questions"]:
                interval = question["mean_range"]
                rows.append(
                    {
                        "curriculum": report["curriculum"],
                        "class": report["class_label"],
                        "subject_code": report["subject_code"],
                        "subject": report["subject_name"],
                        "faculty": report["faculty_name"],
                        "criterion": criterion["name"],
                        "question": question["text"],
                        "responses": question["responses"],
                        **{
                            f"rated_{rating}": question["counts"][str(rating)]
                            for rating in RATINGS
                        },
                        # Blank, never zero, when withheld. A zero here would be
                        # read as a unanimous worst score by anyone opening the
                        # file in a spreadsheet.
                        "mean": "" if question["mean"] is None else question["mean"],
                        "mean_low": "" if interval is None else interval[0],
                        "mean_high": "" if interval is None else interval[1],
                        "reliability": question["reliability"],
                        "note": RELIABILITY_NOTE[question["reliability"]],
                    }
                )
    return _write(rows, RESULTS_COLUMNS)


# --- The cover summary -----------------------------------------------------


def summary(db: Session, term: AcademicTerm, curriculum: str | None = None) -> dict:
    """What goes on the front page of the return."""
    reports = assignment_reports(db, term, curriculum=curriculum)

    eligible = sum(r["eligible_students"] for r in reports)
    responses = sum(r["responses"] for r in reports)
    questionnaire = (
        questionnaire_for(db, term.id, curriculum)
        if curriculum is not None
        else term_questionnaire(db, term.id)
    )

    rated = [r for r in reports if r["mean"] is not None]
    withheld = [r for r in reports if r["mean"] is None]

    return {
        "institution": settings.institution_name,
        "term": {
            "id": term.id,
            "year": term.year,
            "semester": term.semester,
            "label": term_label(term),
            "status": term.status.value,
        },
        "curriculum": curriculum,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "criteria": len(questionnaire),
        "questions": sum(len(questions) for _criterion, questions in questionnaire),
        "assignments": len(reports),
        "faculty": len({r["faculty_id"] for r in reports}),
        "classes": len({r["class_group_id"] for r in reports}),
        "students_eligible": eligible,
        "responses": responses,
        "response_rate": _safe_ratio(responses, eligible),
        "assignments_with_published_means": len(rated),
        "assignments_below_threshold": len(withheld),
        "minimum_responses_for_mean": MIN_RESPONSES_FOR_MEAN,
        "assignment_reports": reports,
    }

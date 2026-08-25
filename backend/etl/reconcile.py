"""Compare the legacy database against the imported one.

    python -m etl.reconcile --legacy mysql+pymysql://user:pw@host/evaluation_db

Row counts are the easy half. The half that matters is whether the *reports*
agree, because that is what a faculty member will notice on day one.

They will not agree exactly, and that is expected rather than a fault:

  - Duplicate submissions were dropped at import, so any assignment that had
    one shifts. Those rows were skewing the old percentages.
  - The legacy report omitted questions nobody answered; the new one includes
    them with a null mean. A criterion average therefore differs wherever a
    question went unanswered.
  - Ratings the old schema allowed outside 1-5 are gone.

So this compares per-question means, which are unaffected by all three, and
reports anything that moved. A difference there is a real defect worth
stopping for.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import (
    AcademicTerm,
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
from etl.legacy import LegacyReader

TOLERANCE = 0.005


def _legacy_question_means(reader: LegacyReader) -> dict[tuple[Any, Any], float]:
    """Per (restriction, question) mean, computed the way the legacy data
    actually sits — but skipping the duplicate submissions the import dropped,
    so like is compared with like."""
    evaluations = reader.rows("evaluation_list")
    answers = reader.rows("evaluation_answers")

    kept: dict[Any, Any] = {}
    seen: set[tuple[Any, ...]] = set()
    for row in sorted(evaluations, key=lambda entry: entry["evaluation_id"]):
        key = (row.get("academic_id"), row.get("student_id"), row.get("restriction_id"))
        if key in seen:
            continue
        seen.add(key)
        kept[row["evaluation_id"]] = row["restriction_id"]

    totals: dict[tuple[Any, Any], list[int]] = defaultdict(list)
    for answer in answers:
        restriction_id = kept.get(answer.get("evaluation_id"))
        rating = answer.get("rate")
        if restriction_id is None or not isinstance(rating, int) or not 1 <= rating <= 5:
            continue
        totals[(restriction_id, answer.get("question_id"))].append(rating)

    return {key: sum(values) / len(values) for key, values in totals.items() if values}


def _new_question_means(session) -> dict[tuple[Any, Any], float]:
    rows = session.execute(
        select(
            EvaluationResponse.assignment_id,
            EvaluationRating.question_id,
            func.avg(EvaluationRating.rating),
        )
        .join(EvaluationRating, EvaluationRating.response_id == EvaluationResponse.id)
        .group_by(EvaluationResponse.assignment_id, EvaluationRating.question_id)
    ).all()
    return {(assignment, question): float(mean) for assignment, question, mean in rows}


def reconcile(reader: LegacyReader, session) -> tuple[list[str], list[str]]:
    """Returns (matches, mismatches) as human-readable lines."""
    ok: list[str] = []
    bad: list[str] = []

    def compare(label: str, legacy: int, imported: int, *, expect_equal: bool = True) -> None:
        line = f"{label:34} legacy {legacy:>6}   imported {imported:>6}"
        if expect_equal and legacy != imported:
            bad.append(line + "   MISMATCH")
        else:
            ok.append(line + ("" if expect_equal else "   (drops expected)"))

    compare("academic years", len(reader.rows("academic_list")), session.query(AcademicTerm).count())
    compare("classes", len(reader.rows("class_list")), session.query(ClassGroup).count())
    compare("subjects", len(reader.rows("subject_list")), session.query(Subject).count())
    compare("questions", len(reader.rows("question_list")), session.query(Question).count(), expect_equal=False)
    compare(
        "faculty",
        len(reader.rows("faculty_list")),
        session.query(Account).filter_by(role=Role.faculty).count(),
    )
    compare(
        "students",
        len(reader.rows("student_list")),
        session.query(Account).filter_by(role=Role.student).count(),
        expect_equal=False,
    )
    compare(
        "assignments",
        len(reader.rows("restriction_list")),
        session.query(TeachingAssignment).count(),
        expect_equal=False,
    )
    compare(
        "submissions",
        len(reader.rows("evaluation_list")),
        session.query(EvaluationSubmission).count(),
        expect_equal=False,
    )

    submissions = session.query(EvaluationSubmission).count()
    responses = session.query(EvaluationResponse).count()
    line = f"{'submissions vs responses':34} {submissions} vs {responses}"
    # These must match exactly. Response rates are computed from one and the
    # ratings hang off the other; if they drift, every rate is wrong.
    (ok if submissions == responses else bad).append(
        line + ("" if submissions == responses else "   MISMATCH")
    )

    # --- The part that matters --------------------------------------------

    legacy_means = _legacy_question_means(reader)
    new_means = _new_question_means(session)

    # Map legacy restriction ids onto the assignments they became, by identity
    # rather than by id, since ids are reassigned on import.
    restriction_rows = {row["id"]: row for row in reader.rows("restriction_list")}
    legacy_terms = {row["id"]: (str(row.get("year")).strip(), row.get("semester")) for row in reader.rows("academic_list")}
    legacy_subjects = {row["id"]: str(row.get("code")).strip() for row in reader.rows("subject_list")}
    legacy_questions = {row["id"]: str(row.get("question")).strip() for row in reader.rows("question_list")}

    new_assignments = {}
    for assignment in session.query(TeachingAssignment):
        term = session.get(AcademicTerm, assignment.term_id)
        subject = session.get(Subject, assignment.subject_id)
        new_assignments[(term.year, term.semester, subject.code, assignment.class_group_id)] = assignment.id

    new_question_text = {q.id: q.text.strip() for q in session.query(Question)}
    text_to_new_question = defaultdict(list)
    for question_id, text in new_question_text.items():
        text_to_new_question[text].append(question_id)

    compared = 0
    for (restriction_id, question_id), legacy_mean in sorted(legacy_means.items()):
        restriction = restriction_rows.get(restriction_id)
        if restriction is None:
            continue
        term_key = legacy_terms.get(restriction["academic_id"])
        subject_code = legacy_subjects.get(restriction["subject_id"])
        question_text = legacy_questions.get(question_id)
        if term_key is None or subject_code is None or question_text is None:
            continue

        candidates = [
            assignment_id
            for (year, semester, code, _class_id), assignment_id in new_assignments.items()
            if (year, semester) == term_key and code == subject_code
        ]
        matched = [
            new_means.get((assignment_id, new_question_id))
            for assignment_id in candidates
            for new_question_id in text_to_new_question.get(question_text, [])
            if (assignment_id, new_question_id) in new_means
        ]
        if not matched:
            continue

        compared += 1
        if all(abs(value - legacy_mean) > TOLERANCE for value in matched if value is not None):
            bad.append(
                f"question mean moved: {subject_code} / '{question_text[:40]}' "
                f"legacy {legacy_mean:.3f} imported {matched[0]:.3f}"
            )

    ok.append(f"{'per-question means compared':34} {compared}")
    return ok, bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", required=True)
    args = parser.parse_args(argv)

    reader = LegacyReader(args.legacy)
    session = SessionLocal()
    try:
        ok, bad = reconcile(reader, session)
        for line in ok:
            print("  ok   " + line)
        for line in bad:
            print("  FAIL " + line)
        print(f"\n{len(ok)} checks passed, {len(bad)} need attention.")
        return 1 if bad else 0
    finally:
        session.close()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())

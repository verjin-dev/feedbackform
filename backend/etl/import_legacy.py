"""Migrate the legacy PHP database into the new schema.

Two modes, and the order matters:

    python -m etl.import_legacy analyse --legacy mysql+pymysql://user:pw@host/evaluation_db
    python -m etl.import_legacy import  --legacy mysql+pymysql://user:pw@host/evaluation_db

`analyse` writes nothing. It reports everything the new schema will refuse and
everything that changes meaning on the way across, so those decisions get made
deliberately instead of surfacing as a failed import halfway through a
cutover window. `import` refuses to run while any blocker is outstanding.

The legacy database has no foreign keys, no unique constraints beyond primary
keys and no check constraints, so it can hold data the new schema cannot:
duplicate submissions, ratings outside 1-5, students in classes that no longer
exist, the same email in two of the three account tables. None of that is
hypothetical — it is what an unconstrained schema accumulates over four years.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    AcademicTerm,
    Account,
    ClassGroup,
    Criterion,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Question,
    Role,
    Subject,
    TeachingAssignment,
    TermStatus,
)
from etl.legacy import BLOCKER, NOTE, WARNING, Finding, LegacyReader

STATUS_MAP = {0: TermStatus.pending, 1: TermStatus.open, 2: TermStatus.closed}

# Column limits in the new schema. The legacy columns were `text` regardless of
# what they held.
LIMITS = {
    "academic_term.year": 20,
    "class_group.curriculum": 100,
    "class_group.level": 50,
    "class_group.section": 50,
    "subject.code": 50,
    "subject.name": 255,
    "criterion.name": 255,
    "account.first_name": 100,
    "account.last_name": 100,
    "account.email": 255,
    "account.school_id": 50,
}

ACCOUNT_SOURCES = (
    ("users", Role.admin),
    ("faculty_list", Role.faculty),
    ("student_list", Role.student),
)


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _email(value: Any) -> str:
    return _clean(value).lower()


@dataclass
class Summary:
    created: Counter = field(default_factory=Counter)
    skipped: Counter = field(default_factory=Counter)

    def render(self) -> str:
        lines = ["Created:"]
        lines += [f"  {name:24} {count}" for name, count in sorted(self.created.items())]
        if self.skipped:
            lines.append("Skipped:")
            lines += [f"  {name:24} {count}" for name, count in sorted(self.skipped.items())]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyse(reader: LegacyReader) -> list[Finding]:
    findings: list[Finding] = []

    missing = reader.missing_tables()
    if missing:
        findings.append(
            Finding(
                BLOCKER,
                "missing-tables",
                "Legacy tables not found; is this the right database?",
                missing,
            )
        )
        return findings

    terms = reader.rows("academic_list")
    classes = reader.rows("class_list")
    subjects = reader.rows("subject_list")
    criteria = reader.rows("criteria_list")
    questions = reader.rows("question_list")
    restrictions = reader.rows("restriction_list")
    evaluations = reader.rows("evaluation_list")
    answers = reader.rows("evaluation_answers")

    accounts: list[tuple[str, Role, dict[str, Any]]] = []
    for table, role in ACCOUNT_SOURCES:
        for row in reader.rows(table):
            accounts.append((table, role, row))

    # --- Accounts ---------------------------------------------------------

    by_email: dict[str, list[str]] = defaultdict(list)
    for table, _role, row in accounts:
        email = _email(row.get("email"))
        if email == "":
            findings.append(
                Finding(BLOCKER, "blank-email", f"{table} id={row.get('id')} has no email")
            )
        else:
            by_email[email].append(f"{table}#{row.get('id')}")

    for email, sources in by_email.items():
        if len(sources) > 1:
            findings.append(
                Finding(
                    BLOCKER,
                    "duplicate-email",
                    f"'{email}' appears in more than one account table; the new "
                    "schema has one account per address",
                    sources,
                )
            )

    by_school_id: dict[str, list[str]] = defaultdict(list)
    for table, _role, row in accounts:
        school_id = _clean(row.get("school_id"))
        if school_id:
            by_school_id[school_id].append(f"{table}#{row.get('id')}")
    for school_id, sources in by_school_id.items():
        if len(sources) > 1:
            findings.append(
                Finding(
                    BLOCKER,
                    "duplicate-school-id",
                    f"Institutional id '{school_id}' is used by more than one account",
                    sources,
                )
            )

    class_ids = {row["id"] for row in classes}
    for table, role, row in accounts:
        if role is not Role.student:
            continue
        if row.get("class_id") not in class_ids:
            findings.append(
                Finding(
                    BLOCKER,
                    "student-without-class",
                    f"student_list#{row.get('id')} references class_id="
                    f"{row.get('class_id')}, which does not exist. Students must "
                    "belong to a class.",
                )
            )

    for table, _role, row in accounts:
        password = _clean(row.get("password"))
        if len(password) != 32 or not all(c in "0123456789abcdefABCDEF" for c in password):
            findings.append(
                Finding(
                    WARNING,
                    "unusable-password",
                    f"{table}#{row.get('id')} has no usable MD5 hash; this account "
                    "will need a password reset before it can sign in",
                )
            )

    # --- Field lengths ----------------------------------------------------

    def check_length(target: str, value: Any, label: str) -> None:
        limit = LIMITS[target]
        if len(_clean(value)) > limit:
            findings.append(
                Finding(
                    WARNING,
                    "too-long",
                    f"{label} exceeds {limit} characters for {target} and will be truncated",
                )
            )

    for row in terms:
        check_length("academic_term.year", row.get("year"), f"academic_list#{row['id']}.year")
    for row in classes:
        for column in ("curriculum", "level", "section"):
            check_length(f"class_group.{column}", row.get(column), f"class_list#{row['id']}.{column}")
    for row in subjects:
        check_length("subject.code", row.get("code"), f"subject_list#{row['id']}.code")
        check_length("subject.name", row.get("subject"), f"subject_list#{row['id']}.subject")
    for row in criteria:
        check_length("criterion.name", row.get("criteria"), f"criteria_list#{row['id']}.criteria")
    for table, _role, row in accounts:
        check_length("account.first_name", row.get("firstname"), f"{table}#{row['id']}.firstname")
        check_length("account.last_name", row.get("lastname"), f"{table}#{row['id']}.lastname")
        check_length("account.email", row.get("email"), f"{table}#{row['id']}.email")
        check_length("account.school_id", row.get("school_id"), f"{table}#{row['id']}.school_id")

    # --- Terms ------------------------------------------------------------

    current = [row["id"] for row in terms if row.get("is_default")]
    if len(current) > 1:
        findings.append(
            Finding(
                WARNING,
                "several-current-terms",
                "More than one academic year is marked default; only the highest id "
                "will be made current",
                current,
            )
        )
    if not current and terms:
        findings.append(
            Finding(
                WARNING,
                "no-current-term",
                "No academic year is marked default; nothing will be current after "
                "import and students will see nothing until one is activated",
            )
        )

    seen_terms: set[tuple[str, Any]] = set()
    for row in terms:
        key = (_clean(row.get("year")), row.get("semester"))
        if key in seen_terms:
            findings.append(
                Finding(BLOCKER, "duplicate-term", f"Year and semester {key} appears twice")
            )
        seen_terms.add(key)

    for row in terms:
        if row.get("status") not in STATUS_MAP:
            findings.append(
                Finding(
                    WARNING,
                    "unknown-status",
                    f"academic_list#{row['id']} has status={row.get('status')}, which is "
                    "not 0, 1 or 2; it will be imported as closed",
                )
            )

    # --- Reference integrity ----------------------------------------------

    term_ids = {row["id"] for row in terms}
    subject_ids = {row["id"] for row in subjects}
    criterion_ids = {row["id"] for row in criteria}
    faculty_ids = {row["id"] for _t, role, row in accounts if role is Role.faculty}
    student_ids = {row["id"] for _t, role, row in accounts if role is Role.student}

    orphan_questions = [
        row["id"]
        for row in questions
        if row.get("academic_id") not in term_ids or row.get("criteria_id") not in criterion_ids
    ]
    if orphan_questions:
        findings.append(
            Finding(
                WARNING,
                "orphan-question",
                "Questions reference an academic year or criterion that no longer "
                "exists and will be skipped",
                orphan_questions,
            )
        )

    orphan_restrictions = [
        row["id"]
        for row in restrictions
        if row.get("academic_id") not in term_ids
        or row.get("faculty_id") not in faculty_ids
        or row.get("class_id") not in class_ids
        or row.get("subject_id") not in subject_ids
    ]
    if orphan_restrictions:
        findings.append(
            Finding(
                WARNING,
                "orphan-assignment",
                "Teaching assignments reference rows that no longer exist and will "
                "be skipped, along with any evaluations against them",
                orphan_restrictions,
            )
        )

    seen_assignment: set[tuple[Any, ...]] = set()
    for row in restrictions:
        key = (
            row.get("academic_id"),
            row.get("faculty_id"),
            row.get("class_id"),
            row.get("subject_id"),
        )
        if key in seen_assignment:
            findings.append(
                Finding(
                    WARNING,
                    "duplicate-assignment",
                    f"Assignment {key} appears more than once; duplicates will be merged",
                )
            )
        seen_assignment.add(key)

    # --- Evaluations ------------------------------------------------------

    restriction_ids = {row["id"] for row in restrictions if row["id"] not in orphan_restrictions}

    duplicate_submissions: list[Any] = []
    seen_submission: set[tuple[Any, ...]] = set()
    for row in sorted(evaluations, key=lambda entry: entry["evaluation_id"]):
        key = (row.get("academic_id"), row.get("student_id"), row.get("restriction_id"))
        if key in seen_submission:
            duplicate_submissions.append(row["evaluation_id"])
        seen_submission.add(key)

    if duplicate_submissions:
        findings.append(
            Finding(
                WARNING,
                "duplicate-submission",
                "The same student submitted more than once for the same assignment. "
                "Nothing prevented this before. Only the earliest is kept, and the "
                "reported percentages will change accordingly",
                duplicate_submissions,
            )
        )

    orphan_evaluations = [
        row["evaluation_id"]
        for row in evaluations
        if row.get("restriction_id") not in restriction_ids
        or row.get("student_id") not in student_ids
    ]
    if orphan_evaluations:
        findings.append(
            Finding(
                WARNING,
                "orphan-evaluation",
                "Evaluations reference a student or assignment that no longer exists "
                "and will be skipped",
                orphan_evaluations,
            )
        )

    evaluation_ids = {row["evaluation_id"] for row in evaluations}
    question_ids = {row["id"] for row in questions if row["id"] not in orphan_questions}

    bad_ratings = [
        (row.get("evaluation_id"), row.get("question_id"), row.get("rate"))
        for row in answers
        if not isinstance(row.get("rate"), int) or not 1 <= row["rate"] <= 5
    ]
    if bad_ratings:
        findings.append(
            Finding(
                BLOCKER,
                "rating-out-of-range",
                "Ratings outside 1-5 exist. The new schema rejects them, so they must "
                "be corrected or deleted before importing",
                bad_ratings,
            )
        )

    orphan_answers = sum(
        1
        for row in answers
        if row.get("evaluation_id") not in evaluation_ids
        or row.get("question_id") not in question_ids
    )
    if orphan_answers:
        findings.append(
            Finding(
                WARNING,
                "orphan-answer",
                f"{orphan_answers} answers reference an evaluation or question that no "
                "longer exists and will be skipped",
            )
        )

    findings.append(
        Finding(
            NOTE,
            "anonymity",
            f"{len(evaluations)} evaluations will be imported with the student link "
            "removed. Participation is preserved so response rates still work, but "
            "no rating will be attributable to a student afterwards. This is "
            "one-way.",
        )
    )
    findings.append(
        Finding(
            NOTE,
            "passwords",
            f"{len(accounts)} accounts will carry their MD5 hash into legacy_md5 and "
            "be rehashed with Argon2id on first sign-in.",
        )
    )

    return findings


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def run_import(reader: LegacyReader, session: Session, *, seed: int | None = None) -> Summary:
    summary = Summary()
    rng = random.Random(seed)

    terms = reader.rows("academic_list")
    classes = reader.rows("class_list")
    subjects = reader.rows("subject_list")
    criteria = reader.rows("criteria_list")
    questions = reader.rows("question_list")
    restrictions = reader.rows("restriction_list")
    evaluations = reader.rows("evaluation_list")
    answers = reader.rows("evaluation_answers")

    # --- Reference data ---------------------------------------------------

    current_term_id = max((row["id"] for row in terms if row.get("is_default")), default=None)

    term_map: dict[Any, AcademicTerm] = {}
    for row in sorted(terms, key=lambda entry: entry["id"]):
        term = AcademicTerm(
            year=_clean(row.get("year"))[: LIMITS["academic_term.year"]],
            semester=int(row.get("semester") or 1),
            status=STATUS_MAP.get(row.get("status"), TermStatus.closed),
            is_current=row["id"] == current_term_id,
        )
        session.add(term)
        term_map[row["id"]] = term
        summary.created["academic_term"] += 1

    class_map: dict[Any, ClassGroup] = {}
    for row in sorted(classes, key=lambda entry: entry["id"]):
        group = ClassGroup(
            curriculum=_clean(row.get("curriculum"))[: LIMITS["class_group.curriculum"]],
            level=_clean(row.get("level"))[: LIMITS["class_group.level"]],
            section=_clean(row.get("section"))[: LIMITS["class_group.section"]],
        )
        session.add(group)
        class_map[row["id"]] = group
        summary.created["class_group"] += 1

    subject_map: dict[Any, Subject] = {}
    for row in sorted(subjects, key=lambda entry: entry["id"]):
        subject = Subject(
            code=_clean(row.get("code"))[: LIMITS["subject.code"]],
            name=_clean(row.get("subject"))[: LIMITS["subject.name"]],
            description=_clean(row.get("description")) or None,
        )
        session.add(subject)
        subject_map[row["id"]] = subject
        summary.created["subject"] += 1

    criterion_map: dict[Any, Criterion] = {}
    for position, row in enumerate(
        sorted(criteria, key=lambda entry: (abs(int(entry.get("order_by") or 0)), entry["id"])),
        start=1,
    ):
        criterion = Criterion(
            name=_clean(row.get("criteria"))[: LIMITS["criterion.name"]],
            position=position,
        )
        session.add(criterion)
        criterion_map[row["id"]] = criterion
        summary.created["criterion"] += 1

    session.flush()

    # --- Accounts ---------------------------------------------------------

    account_map: dict[tuple[str, Any], Account] = {}
    for table, role in ACCOUNT_SOURCES:
        for row in sorted(reader.rows(table), key=lambda entry: entry["id"]):
            class_group = class_map.get(row.get("class_id")) if role is Role.student else None
            if role is Role.student and class_group is None:
                summary.skipped["student (no class)"] += 1
                continue

            md5 = _clean(row.get("password")).lower()
            usable = len(md5) == 32 and all(c in "0123456789abcdef" for c in md5)

            account = Account(
                role=role,
                first_name=_clean(row.get("firstname"))[: LIMITS["account.first_name"]] or "Unknown",
                last_name=_clean(row.get("lastname"))[: LIMITS["account.last_name"]] or "Unknown",
                email=_email(row.get("email"))[: LIMITS["account.email"]],
                school_id=(_clean(row.get("school_id"))[: LIMITS["account.school_id"]] or None),
                # Never an Argon2 hash at import: the account holds only what the
                # legacy app held, and is upgraded on first successful sign-in.
                password_hash=None if usable else _unusable_placeholder(),
                legacy_md5=md5 if usable else None,
                class_group_id=class_group.id if class_group else None,
            )
            session.add(account)
            account_map[(table, row["id"])] = account
            summary.created[f"account ({role.value})"] += 1

    session.flush()

    # --- Assignments ------------------------------------------------------

    assignment_map: dict[Any, TeachingAssignment] = {}
    seen_assignment: dict[tuple[Any, ...], TeachingAssignment] = {}
    for row in sorted(restrictions, key=lambda entry: entry["id"]):
        term = term_map.get(row.get("academic_id"))
        faculty = account_map.get(("faculty_list", row.get("faculty_id")))
        group = class_map.get(row.get("class_id"))
        subject = subject_map.get(row.get("subject_id"))

        if term is None or faculty is None or group is None or subject is None:
            summary.skipped["assignment (orphaned)"] += 1
            continue

        key = (term.id, faculty.id, group.id, subject.id)
        if key in seen_assignment:
            # Duplicates in the legacy table collapse onto one row; evaluations
            # against either still land on it.
            assignment_map[row["id"]] = seen_assignment[key]
            summary.skipped["assignment (duplicate)"] += 1
            continue

        assignment = TeachingAssignment(
            term_id=term.id, faculty_id=faculty.id, class_group_id=group.id, subject_id=subject.id
        )
        session.add(assignment)
        seen_assignment[key] = assignment
        assignment_map[row["id"]] = assignment
        summary.created["teaching_assignment"] += 1

    # --- Questions --------------------------------------------------------

    question_map: dict[Any, Question] = {}
    by_term: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in questions:
        by_term[row.get("academic_id")].append(row)

    for legacy_term_id, rows in by_term.items():
        term = term_map.get(legacy_term_id)
        if term is None:
            summary.skipped["question (orphaned)"] += len(rows)
            continue
        ordered = sorted(rows, key=lambda entry: (abs(int(entry.get("order_by") or 0)), entry["id"]))
        for position, row in enumerate(ordered, start=1):
            criterion = criterion_map.get(row.get("criteria_id"))
            if criterion is None:
                summary.skipped["question (orphaned)"] += 1
                continue
            question = Question(
                term_id=term.id,
                criterion_id=criterion.id,
                text=_clean(row.get("question")),
                position=position,
            )
            session.add(question)
            question_map[row["id"]] = question
            summary.created["question"] += 1

    session.flush()

    # --- Evaluations, split in two ----------------------------------------

    answers_by_evaluation: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in answers:
        answers_by_evaluation[row.get("evaluation_id")].append(row)

    keepers: list[dict[str, Any]] = []
    seen_submission: set[tuple[Any, ...]] = set()
    for row in sorted(evaluations, key=lambda entry: entry["evaluation_id"]):
        assignment = assignment_map.get(row.get("restriction_id"))
        student = account_map.get(("student_list", row.get("student_id")))
        if assignment is None or student is None:
            summary.skipped["evaluation (orphaned)"] += 1
            continue

        key = (assignment.term_id, student.id, assignment.id)
        if key in seen_submission:
            summary.skipped["evaluation (duplicate)"] += 1
            continue
        seen_submission.add(key)
        keepers.append(row)

        session.add(
            EvaluationSubmission(
                term_id=assignment.term_id, student_id=student.id, assignment_id=assignment.id
            )
        )
        summary.created["evaluation_submission"] += 1

    # Responses are written in a shuffled order so their row order — and, with
    # UUIDv7 ids, their timestamps — cannot be lined up against the submissions
    # above to undo the split. See the note in app/models/evaluation.py.
    rng.shuffle(keepers)

    for row in keepers:
        assignment = assignment_map[row["restriction_id"]]
        response = EvaluationResponse(term_id=assignment.term_id, assignment_id=assignment.id)
        session.add(response)
        session.flush()
        summary.created["evaluation_response"] += 1

        written: set[Any] = set()
        for answer in answers_by_evaluation.get(row["evaluation_id"], []):
            question = question_map.get(answer.get("question_id"))
            rating = answer.get("rate")
            if question is None or not isinstance(rating, int) or not 1 <= rating <= 5:
                summary.skipped["answer (invalid)"] += 1
                continue
            if question.id in written:
                summary.skipped["answer (duplicate)"] += 1
                continue
            written.add(question.id)
            session.add(
                EvaluationRating(
                    response_id=response.id, question_id=question.id, rating=rating
                )
            )
            summary.created["evaluation_rating"] += 1

    session.commit()
    return summary


def _unusable_placeholder() -> str:
    """A value no password can produce, for accounts whose legacy hash is not a
    usable MD5. They satisfy the "some credential present" constraint and can
    only get in via a reset."""
    return "reset-required-" + hashlib.sha256(random.randbytes(16)).hexdigest()[:32]


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("analyse", "import"))
    parser.add_argument("--legacy", required=True, help="SQLAlchemy URL for the legacy database")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Import despite blockers. Rows the new schema rejects are skipped.",
    )
    args = parser.parse_args(argv)

    reader = LegacyReader(args.legacy)
    try:
        findings = analyse(reader)
        for finding in findings:
            print(finding)

        blockers = [f for f in findings if f.level == BLOCKER]
        print(
            f"\n{len(blockers)} blocker(s), "
            f"{sum(1 for f in findings if f.level == WARNING)} warning(s)."
        )

        if args.mode == "analyse":
            return 1 if blockers else 0

        if blockers and not args.force:
            print("\nRefusing to import while blockers stand. Fix them, or pass --force.")
            return 1

        # Imported here, not at module load: `analyse` writes nothing and
        # must run before the target database exists, but app.core.database
        # builds its engine on import and requires DATABASE_URL.
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            summary = run_import(reader, session)
            print("\n" + summary.render())
        finally:
            session.close()
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())

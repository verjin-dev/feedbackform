from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import require_admin
from app.core.database import get_session
from app.models import (
    Account,
    AcademicTerm,
    ClassGroup,
    EvaluationSubmission,
    Role,
    Subject,
    TeachingAssignment,
)
from app.schemas.management import (
    AssignmentItem,
    AssignmentOut,
    AssignmentReplaceRequest,
)

router = APIRouter(
    prefix="/academic-years/{term_id}/assignments",
    tags=["assignments"],
    dependencies=[Depends(require_admin)],
)


def _serialise(assignment: TeachingAssignment) -> dict:
    return {
        "id": assignment.id,
        "term_id": assignment.term_id,
        "faculty_id": assignment.faculty_id,
        "faculty_name": assignment.faculty.full_name,
        "class_group_id": assignment.class_group_id,
        "class_label": assignment.class_group.label,
        "subject_id": assignment.subject_id,
        "subject_code": assignment.subject.code,
        "subject_name": assignment.subject.name,
    }


def _key(assignment: TeachingAssignment) -> AssignmentItem:
    return AssignmentItem(
        faculty_id=assignment.faculty_id,
        class_group_id=assignment.class_group_id,
        subject_id=assignment.subject_id,
    )


@router.get("", response_model=list[AssignmentOut])
def list_assignments(term_id: int, db: Session = Depends(get_session)):
    crud.get_or_404(db, AcademicTerm, term_id)
    rows = db.scalars(
        select(TeachingAssignment).where(TeachingAssignment.term_id == term_id)
    ).unique().all()
    return [_serialise(row) for row in rows]


@router.put("", response_model=list[AssignmentOut])
def replace_assignments(
    term_id: int,
    payload: AssignmentReplaceRequest,
    db: Session = Depends(get_session),
):
    """Replace the whole assignment set for a term, in one transaction.

    The legacy save_restriction ran `DELETE FROM restriction_list WHERE id NOT
    IN (...)` and then re-inserted. Two consequences it never handled:

      - With no foreign keys, deleting an assignment left its evaluations
        pointing at a row that no longer existed.
      - Now that the foreign key exists and cascades, the same delete would
        take the collected feedback with it.

    So an assignment that already has submissions against it is refused rather
    than removed. Withdrawing a class mid-term is a real thing an
    administrator might mean to do, but it must be a deliberate act with the
    consequences visible — not a side effect of saving the matrix.
    """
    crud.get_or_404(db, AcademicTerm, term_id)

    requested = set(payload.assignments)
    if requested:
        _validate_references(db, requested)

    existing = {
        _key(row): row
        for row in db.scalars(
            select(TeachingAssignment).where(TeachingAssignment.term_id == term_id)
        ).unique().all()
    }

    doomed = [row for key, row in existing.items() if key not in requested]
    _refuse_if_evaluated(db, doomed)

    for row in doomed:
        db.delete(row)

    for key in requested - set(existing):
        db.add(
            TeachingAssignment(
                term_id=term_id,
                faculty_id=key.faculty_id,
                class_group_id=key.class_group_id,
                subject_id=key.subject_id,
            )
        )

    with crud.integrity_guard(db, "That set of assignments could not be saved."):
        db.commit()

    rows = db.scalars(
        select(TeachingAssignment).where(TeachingAssignment.term_id == term_id)
    ).unique().all()
    return [_serialise(row) for row in rows]


def _validate_references(db: Session, requested: set[AssignmentItem]) -> None:
    """Check every referenced row exists, and that faculty really are faculty.

    Foreign keys would catch the first case as a 409; doing it here produces a
    message that names what is wrong instead.
    """
    faculty_ids = {item.faculty_id for item in requested}
    class_ids = {item.class_group_id for item in requested}
    subject_ids = {item.subject_id for item in requested}

    found_faculty = set(
        db.scalars(
            select(Account.id).where(
                Account.id.in_(faculty_ids), Account.role == Role.faculty
            )
        ).all()
    )
    if missing := faculty_ids - found_faculty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a faculty account: {sorted(missing)}",
        )

    found_classes = set(
        db.scalars(select(ClassGroup.id).where(ClassGroup.id.in_(class_ids))).all()
    )
    if missing := class_ids - found_classes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No such class: {sorted(missing)}",
        )

    found_subjects = set(
        db.scalars(select(Subject.id).where(Subject.id.in_(subject_ids))).all()
    )
    if missing := subject_ids - found_subjects:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No such subject: {sorted(missing)}",
        )


def _refuse_if_evaluated(db: Session, doomed: list[TeachingAssignment]) -> None:
    if not doomed:
        return

    evaluated = set(
        db.scalars(
            select(EvaluationSubmission.assignment_id).where(
                EvaluationSubmission.assignment_id.in_([row.id for row in doomed])
            )
        ).all()
    )
    if not evaluated:
        return

    described = sorted(
        f"{row.faculty.full_name} — {row.subject.code} ({row.class_group.label})"
        for row in doomed
        if row.id in evaluated
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "These assignments already have submitted evaluations and cannot be "
            "removed: " + "; ".join(described)
        ),
    )

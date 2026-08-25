from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.core.database import get_session
from app.models import (
    AcademicTerm,
    Account,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    Question,
    TeachingAssignment,
    TermStatus,
)
from app.schemas.evaluation import (
    CriterionBlock,
    EvaluationSubmitRequest,
    PendingAssignmentOut,
    QuestionnaireOut,
    SubmissionReceipt,
    TermBrief,
)
from app.services.reporting import term_questionnaire

router = APIRouter(tags=["evaluation"], dependencies=[Depends(require_student)])


def _current_term(db: Session) -> AcademicTerm:
    term = db.scalar(select(AcademicTerm).where(AcademicTerm.is_current.is_(True)))
    if term is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No academic term is currently active.",
        )
    return term


def _pending_query(term: AcademicTerm, student: Account):
    """Assignments for this student's class that they have not yet submitted.

    The legacy page built this with a correlated NOT IN over evaluation_list
    filtered by student_id, then relied on it to prevent duplicates. It is now
    only what drives the UI; the unique constraint is what enforces the rule.
    """
    already_submitted = select(EvaluationSubmission.assignment_id).where(
        EvaluationSubmission.term_id == term.id,
        EvaluationSubmission.student_id == student.id,
    )
    return (
        select(TeachingAssignment)
        .where(
            TeachingAssignment.term_id == term.id,
            TeachingAssignment.class_group_id == student.class_group_id,
            TeachingAssignment.id.not_in(already_submitted),
        )
        .order_by(TeachingAssignment.id)
    )


@router.get("/me/assignments/pending", response_model=list[PendingAssignmentOut])
def pending_assignments(
    student: Account = Depends(require_student),
    db: Session = Depends(get_session),
):
    term = _current_term(db)
    rows = db.scalars(_pending_query(term, student)).unique().all()
    return [
        PendingAssignmentOut(
            assignment_id=row.id,
            faculty_id=row.faculty_id,
            faculty_name=row.faculty.full_name,
            subject_id=row.subject_id,
            subject_code=row.subject.code,
            subject_name=row.subject.name,
        )
        for row in rows
    ]


@router.get("/me/questionnaire", response_model=QuestionnaireOut)
def questionnaire(
    student: Account = Depends(require_student),
    db: Session = Depends(get_session),
):
    term = _current_term(db)
    return QuestionnaireOut(
        term=TermBrief.model_validate(term),
        criteria=[
            CriterionBlock(
                criterion_id=criterion.id,
                name=criterion.name,
                questions=[{"id": q.id, "text": q.text} for q in questions],
            )
            for criterion, questions in term_questionnaire(db, term.id)
        ],
    )


@router.post(
    "/evaluations", response_model=SubmissionReceipt, status_code=status.HTTP_201_CREATED
)
def submit_evaluation(
    payload: EvaluationSubmitRequest,
    student: Account = Depends(require_student),
    db: Session = Depends(get_session),
):
    term = _current_term(db)

    if term.status is not TermStatus.open:
        detail = (
            "Evaluation has not opened yet."
            if term.status is TermStatus.pending
            else "Evaluation is closed for this term."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    assignment = db.get(TeachingAssignment, payload.assignment_id)
    # A 404 for an assignment belonging to another class would confirm it
    # exists, so an assignment this student cannot rate is simply not found.
    if (
        assignment is None
        or assignment.term_id != term.id
        or assignment.class_group_id != student.class_group_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such assignment for you."
        )

    expected = set(
        db.scalars(select(Question.id).where(Question.term_id == term.id)).all()
    )
    submitted = {rating.question_id for rating in payload.ratings}

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This term has no questionnaire yet.",
        )
    if submitted != expected:
        # Storing a partial evaluation would quietly skew every mean it feeds.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Every question must be answered exactly once. "
                f"Missing: {sorted(expected - submitted)}. "
                f"Not part of this questionnaire: {sorted(submitted - expected)}."
            ),
        )

    # Both halves in one transaction, with nothing linking them. See the note
    # at the top of app/models/evaluation.py.
    #
    # The guard covers the flush as well as the commit: the duplicate-
    # submission constraint trips on the INSERT, which the flush below emits
    # in order to obtain the response id.
    try:
        db.add(
            EvaluationSubmission(
                term_id=term.id, student_id=student.id, assignment_id=assignment.id
            )
        )
        response = EvaluationResponse(term_id=term.id, assignment_id=assignment.id)
        db.add(response)
        db.flush()

        for rating in payload.ratings:
            db.add(
                EvaluationRating(
                    response_id=response.id,
                    question_id=rating.question_id,
                    rating=rating.rating,
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        # The unique constraint, not the UI filter, is what stops a second
        # submission — including two arriving concurrently.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted feedback for this subject.",
        ) from None

    return SubmissionReceipt(
        assignment_id=assignment.id, answers_recorded=len(payload.ratings)
    )

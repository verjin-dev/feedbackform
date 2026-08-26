from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.core import i18n
from app.core.database import get_session
from app.models import (
    AcademicTerm,
    Account,
    ClassGroup,
    EvaluationRating,
    EvaluationResponse,
    EvaluationSubmission,
    TeachingAssignment,
    TermStatus,
)
from app.schemas.evaluation import (
    CommentPromptOut,
    CriterionBlock,
    EvaluationSubmitRequest,
    PendingAssignmentOut,
    QuestionnaireOut,
    SubmissionReceipt,
    TermBrief,
)
from app.services import comments as comment_service
from app.services.reporting import questionnaire_for

router = APIRouter(tags=["evaluation"], dependencies=[Depends(require_student)])


def _current_term(db: Session) -> AcademicTerm:
    term = db.scalar(select(AcademicTerm).where(AcademicTerm.is_current.is_(True)))
    if term is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No academic term is currently active.",
        )
    return term

def _student_questionnaire(db: Session, student: Account, term: AcademicTerm):
    """The core questionnaire plus this student's department block.

    Resolved from the student's own class group rather than passed in, so the
    set the form is drawn from and the set a submission is checked against
    cannot drift apart -- a student answering exactly what they were shown and
    being told a question is missing is the failure this shape rules out.
    """
    group = db.get(ClassGroup, student.class_group_id) if student.class_group_id else None
    return questionnaire_for(db, term.id, group.curriculum if group else None)


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
    # Every assignment a student can rate belongs to their own class group, so
    # one student is asked one questionnaire: the shared core plus whatever
    # their department adds.
    #
    # Rendered in the student's language, falling back to English per question:
    # a half-translated questionnaire is readable, one where the untranslated
    # questions disappear is not.
    language = i18n.normalise(student.language)

    return QuestionnaireOut(
        term=TermBrief.model_validate(term),
        language=language,
        criteria=[
            CriterionBlock(
                criterion_id=criterion.id,
                name=criterion.display_name(language),
                questions=[
                    {"id": q.id, "text": q.display_text(language)} for q in questions
                ],
            )
            for criterion, questions in _student_questionnaire(db, student, term)
        ],
        comment_prompts=[
            CommentPromptOut(
                prompt=prompt, text=i18n.comment_prompt(prompt.value, language)
            )
            for prompt in comment_service.PROMPT_TEXT
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

    expected = {
        question.id
        for _, questions in _student_questionnaire(db, student, term)
        for question in questions
    }
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

        # Same transaction as the ratings: a submission is one act, and a
        # comment stored without its ratings would be an orphan nobody could
        # interpret.
        written_comments = comment_service.save_comments(
            db,
            response,
            [(entry.prompt, entry.text) for entry in payload.comments],
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
        assignment_id=assignment.id,
        answers_recorded=len(payload.ratings),
        comments_recorded=written_comments,
    )

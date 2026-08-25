"""Reference-data CRUD: terms, classes, subjects, criteria, questions.

Five resources sharing one shape, so they share one set of helpers from
app.api.crud rather than repeating error handling five times. Every route here
is admin-only; the dependency is declared on the router so a new route cannot
be added without one.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import require_admin
from app.core.database import get_session
from app.models import AcademicTerm, ClassGroup, Criterion, Question, Subject
from app.models.base import Base
from app.schemas.reference import (
    AcademicTermCreate,
    AcademicTermOut,
    AcademicTermUpdate,
    ClassGroupCreate,
    ClassGroupOut,
    ClassGroupUpdate,
    CriterionCreate,
    CriterionOut,
    CriterionUpdate,
    QuestionCreate,
    QuestionOut,
    QuestionUpdate,
    ReorderRequest,
    SubjectCreate,
    SubjectOut,
    SubjectUpdate,
)

router = APIRouter(dependencies=[Depends(require_admin)], tags=["reference"])


def _apply_reorder(
    db: Session,
    model: type[Base],
    payload: ReorderRequest,
    scope: dict[str, int] | None = None,
) -> None:
    """Assign positions 1..n from the given order, in one transaction.

    Requires the payload to name every row in scope. Accepting a subset would
    let a stale client silently drop items from the ordering.
    """
    statement = select(model)
    if scope:
        for column, value in scope.items():
            statement = statement.where(getattr(model, column) == value)
    rows = {row.id: row for row in db.scalars(statement).unique().all()}

    if set(payload.ids) != set(rows):
        missing = sorted(set(rows) - set(payload.ids))
        unknown = sorted(set(payload.ids) - set(rows))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The ordering must list every item exactly once. "
                f"Missing: {missing}. Not recognised: {unknown}."
            ),
        )

    for position, row_id in enumerate(payload.ids, start=1):
        rows[row_id].position = position
    db.commit()


# --- Academic terms --------------------------------------------------------

terms = APIRouter(prefix="/academic-years")


@terms.get("", response_model=list[AcademicTermOut])
def list_terms(db: Session = Depends(get_session)):
    return crud.list_all(db, AcademicTerm, AcademicTerm.year.desc(), AcademicTerm.semester)


@terms.post("", response_model=AcademicTermOut, status_code=status.HTTP_201_CREATED)
def create_term(payload: AcademicTermCreate, db: Session = Depends(get_session)):
    return crud.create(
        db, AcademicTerm, payload.model_dump(), "That year and semester already exists."
    )


@terms.get("/{term_id}", response_model=AcademicTermOut)
def get_term(term_id: int, db: Session = Depends(get_session)):
    return crud.get_or_404(db, AcademicTerm, term_id)


@terms.patch("/{term_id}", response_model=AcademicTermOut)
def update_term(
    term_id: int, payload: AcademicTermUpdate, db: Session = Depends(get_session)
):
    term = crud.get_or_404(db, AcademicTerm, term_id)
    return crud.update(
        db,
        term,
        payload.model_dump(exclude_unset=True),
        "That year and semester already exists.",
    )


@terms.delete("/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_term(term_id: int, db: Session = Depends(get_session)):
    term = crud.get_or_404(db, AcademicTerm, term_id)
    if term.is_current:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The current term cannot be deleted. Make another term current first.",
        )
    crud.delete(db, term, "This term still has questions or assignments attached.")


@terms.post("/{term_id}/activate", response_model=AcademicTermOut)
def activate_term(term_id: int, db: Session = Depends(get_session)):
    """Make one term current.

    The legacy `make_default` cleared the previous default in a separate
    statement with nothing enforcing that exactly one row won. Here both writes
    are one transaction, and a partial unique index would reject the result if
    they ever disagreed.
    """
    term = crud.get_or_404(db, AcademicTerm, term_id)

    # Excludes the target row. Clearing it too would leave this ORM object
    # stale against the bulk UPDATE, so reassigning True would emit nothing and
    # activating the already-current term would quietly deactivate it.
    db.execute(
        update(AcademicTerm)
        .where(AcademicTerm.id != term_id, AcademicTerm.is_current.is_(True))
        .values(is_current=False)
    )
    db.flush()
    term.is_current = True

    with crud.integrity_guard(db, "Another term is already current."):
        db.commit()
    db.refresh(term)
    return term


# --- Classes ---------------------------------------------------------------

classes = APIRouter(prefix="/classes")


@classes.get("", response_model=list[ClassGroupOut])
def list_classes(db: Session = Depends(get_session)):
    return crud.list_all(
        db, ClassGroup, ClassGroup.curriculum, ClassGroup.level, ClassGroup.section
    )


@classes.post("", response_model=ClassGroupOut, status_code=status.HTTP_201_CREATED)
def create_class(payload: ClassGroupCreate, db: Session = Depends(get_session)):
    return crud.create(
        db, ClassGroup, payload.model_dump(), "That class already exists."
    )


@classes.get("/{class_id}", response_model=ClassGroupOut)
def get_class(class_id: int, db: Session = Depends(get_session)):
    return crud.get_or_404(db, ClassGroup, class_id)


@classes.patch("/{class_id}", response_model=ClassGroupOut)
def update_class(
    class_id: int, payload: ClassGroupUpdate, db: Session = Depends(get_session)
):
    group = crud.get_or_404(db, ClassGroup, class_id)
    return crud.update(
        db, group, payload.model_dump(exclude_unset=True), "That class already exists."
    )


@classes.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(class_id: int, db: Session = Depends(get_session)):
    group = crud.get_or_404(db, ClassGroup, class_id)
    crud.delete(db, group, "Students or assignments still reference this class.")


# --- Subjects --------------------------------------------------------------

subjects = APIRouter(prefix="/subjects")


@subjects.get("", response_model=list[SubjectOut])
def list_subjects(db: Session = Depends(get_session)):
    return crud.list_all(db, Subject, Subject.code)


@subjects.post("", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_session)):
    return crud.create(db, Subject, payload.model_dump(), "That subject code is already in use.")


@subjects.get("/{subject_id}", response_model=SubjectOut)
def get_subject(subject_id: int, db: Session = Depends(get_session)):
    return crud.get_or_404(db, Subject, subject_id)


@subjects.patch("/{subject_id}", response_model=SubjectOut)
def update_subject(
    subject_id: int, payload: SubjectUpdate, db: Session = Depends(get_session)
):
    subject = crud.get_or_404(db, Subject, subject_id)
    return crud.update(
        db, subject, payload.model_dump(exclude_unset=True), "That subject code is already in use."
    )


@subjects.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(subject_id: int, db: Session = Depends(get_session)):
    subject = crud.get_or_404(db, Subject, subject_id)
    crud.delete(db, subject, "Assignments still reference this subject.")


# --- Criteria --------------------------------------------------------------

criteria = APIRouter(prefix="/criteria")


@criteria.get("", response_model=list[CriterionOut])
def list_criteria(db: Session = Depends(get_session)):
    return crud.list_all(db, Criterion, Criterion.position, Criterion.id)


@criteria.post("", response_model=CriterionOut, status_code=status.HTTP_201_CREATED)
def create_criterion(payload: CriterionCreate, db: Session = Depends(get_session)):
    # New items go to the end rather than colliding at position 0.
    next_position = (db.scalar(select(func.max(Criterion.position))) or 0) + 1
    return crud.create(
        db,
        Criterion,
        {**payload.model_dump(), "position": next_position},
        "That criterion already exists.",
    )


@criteria.get("/{criterion_id}", response_model=CriterionOut)
def get_criterion(criterion_id: int, db: Session = Depends(get_session)):
    return crud.get_or_404(db, Criterion, criterion_id)


@criteria.patch("/{criterion_id}", response_model=CriterionOut)
def update_criterion(
    criterion_id: int, payload: CriterionUpdate, db: Session = Depends(get_session)
):
    criterion = crud.get_or_404(db, Criterion, criterion_id)
    return crud.update(
        db,
        criterion,
        payload.model_dump(exclude_unset=True),
        "That criterion already exists.",
    )


@criteria.delete("/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_criterion(criterion_id: int, db: Session = Depends(get_session)):
    criterion = crud.get_or_404(db, Criterion, criterion_id)
    crud.delete(db, criterion, "Questions still reference this criterion.")


@criteria.put("/order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_criteria(payload: ReorderRequest, db: Session = Depends(get_session)):
    _apply_reorder(db, Criterion, payload)


# --- Questions -------------------------------------------------------------

questions = APIRouter(prefix="/questions")


@questions.get("", response_model=list[QuestionOut])
def list_questions(term_id: int | None = None, db: Session = Depends(get_session)):
    statement = select(Question).order_by(
        Question.criterion_id, Question.position, Question.id
    )
    if term_id is not None:
        statement = statement.where(Question.term_id == term_id)
    return db.scalars(statement).unique().all()


@questions.post("", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_question(payload: QuestionCreate, db: Session = Depends(get_session)):
    crud.get_or_404(db, AcademicTerm, payload.term_id)
    crud.get_or_404(db, Criterion, payload.criterion_id)

    next_position = (
        db.scalar(
            select(func.max(Question.position)).where(Question.term_id == payload.term_id)
        )
        or 0
    ) + 1
    return crud.create(
        db,
        Question,
        {**payload.model_dump(), "position": next_position},
        "That question could not be saved.",
    )


@questions.patch("/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int, payload: QuestionUpdate, db: Session = Depends(get_session)
):
    question = crud.get_or_404(db, Question, question_id)
    data = payload.model_dump(exclude_unset=True)
    if "criterion_id" in data:
        crud.get_or_404(db, Criterion, data["criterion_id"])
    return crud.update(db, question, data, "That question could not be saved.")


@questions.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question_id: int, db: Session = Depends(get_session)):
    question = crud.get_or_404(db, Question, question_id)
    crud.delete(db, question, "This question already has ratings against it.")


@questions.put("/order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_questions(
    term_id: int, payload: ReorderRequest, db: Session = Depends(get_session)
):
    _apply_reorder(db, Question, payload, scope={"term_id": term_id})


for sub in (terms, classes, subjects, criteria, questions):
    router.include_router(sub)

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


def _label(model: type[Base]) -> str:
    return model.__name__


def get_or_404(db: Session, model: type[ModelT], pk: Any) -> ModelT:
    instance = db.get(model, pk)
    if instance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{_label(model)} not found"
        )
    return instance


def list_all(db: Session, model: type[ModelT], *order_by: Any) -> Sequence[ModelT]:
    statement = select(model)
    if order_by:
        statement = statement.order_by(*order_by)
    return db.scalars(statement).unique().all()


@contextmanager
def integrity_guard(db: Session, detail: str) -> Iterator[None]:
    """Turn a constraint violation into a 409 instead of a 500.

    Every uniqueness and referential rule in this schema is enforced by the
    database rather than by a read-then-write check in Python, because the
    latter loses a race. That means the violation surfaces here, and callers
    deserve a usable answer rather than a stack trace.
    """
    try:
        yield
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None


def create(db: Session, model: type[ModelT], data: dict[str, Any], conflict: str) -> ModelT:
    instance = model(**data)
    db.add(instance)
    with integrity_guard(db, conflict):
        db.commit()
    db.refresh(instance)
    return instance


def update(db: Session, instance: ModelT, data: dict[str, Any], conflict: str) -> ModelT:
    for field, value in data.items():
        setattr(instance, field, value)
    with integrity_guard(db, conflict):
        db.commit()
    db.refresh(instance)
    return instance


def delete(db: Session, instance: ModelT, in_use: str) -> None:
    """Deleting a row other rows depend on is a 409, not a 500.

    Foreign keys are declared RESTRICT precisely so this is refused rather than
    quietly cascading. The legacy schema had no foreign keys at all, so the
    same action left orphaned rows behind and nothing complained.
    """
    db.delete(instance)
    with integrity_guard(db, in_use):
        db.commit()

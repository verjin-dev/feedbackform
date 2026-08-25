from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import get_current_account, require_admin
from app.core.database import get_session
from app.core.security import hash_password
from app.models import Account, ClassGroup, Role
from app.schemas.auth import AccountOut
from app.schemas.management import AccountCreate, AccountUpdate

router = APIRouter(
    prefix="/accounts", tags=["accounts"], dependencies=[Depends(require_admin)]
)

DUPLICATE = "That email address or institutional id is already registered."


def _count_active_admins(db: Session, excluding: int | None = None) -> int:
    statement = (
        select(func.count())
        .select_from(Account)
        .where(Account.role == Role.admin, Account.is_active.is_(True))
    )
    if excluding is not None:
        statement = statement.where(Account.id != excluding)
    return db.scalar(statement) or 0


@router.get("", response_model=list[AccountOut])
def list_accounts(
    role: Role | None = None,
    class_group_id: int | None = None,
    db: Session = Depends(get_session),
):
    """One resource for all three kinds of account.

    The legacy app had save_user / save_faculty / save_student as separate
    endpoints over three near-identical tables.
    """
    statement = select(Account).order_by(Account.last_name, Account.first_name)
    if role is not None:
        statement = statement.where(Account.role == role)
    if class_group_id is not None:
        statement = statement.where(Account.class_group_id == class_group_id)
    return db.scalars(statement).unique().all()


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_session)):
    if payload.class_group_id is not None:
        crud.get_or_404(db, ClassGroup, payload.class_group_id)

    data = payload.model_dump(exclude={"password"})
    data["email"] = data["email"].lower()
    data["password_hash"] = hash_password(payload.password)
    return crud.create(db, Account, data, DUPLICATE)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: int, db: Session = Depends(get_session)):
    return crud.get_or_404(db, Account, account_id)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_session),
    actor: Account = Depends(get_current_account),
):
    account = crud.get_or_404(db, Account, account_id)
    data = payload.model_dump(exclude_unset=True)

    if "password" in data:
        password = data.pop("password")
        if password is not None:
            data["password_hash"] = hash_password(password)
            # A password set by an administrator supersedes any migrated hash.
            data["legacy_md5"] = None

    if "email" in data and data["email"] is not None:
        data["email"] = data["email"].lower()

    if "class_group_id" in data and data["class_group_id"] is not None:
        crud.get_or_404(db, ClassGroup, data["class_group_id"])

    if data.get("is_active") is False and account.role is Role.admin:
        if _count_active_admins(db, excluding=account.id) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This is the only active administrator. "
                "Promote another before deactivating it.",
            )

    return crud.update(db, account, data, DUPLICATE)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    db: Session = Depends(get_session),
    actor: Account = Depends(get_current_account),
):
    account = crud.get_or_404(db, Account, account_id)

    if account.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot delete the account you are signed in with.",
        )

    if account.role is Role.admin and _count_active_admins(db, excluding=account.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This is the only active administrator and cannot be deleted.",
        )

    crud.delete(
        db,
        account,
        "This account is referenced by teaching assignments or submitted "
        "evaluations. Deactivate it instead of deleting it.",
    )

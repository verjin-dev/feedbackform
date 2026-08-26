from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import crud
from app.api.deps import get_current_account, require_admin
from app.core.database import get_session
from app.core.security import hash_password
from app.models import Account, ClassGroup, Role
from app.schemas.auth import AccountOut
from app.schemas.import_ import ImportReportOut
from app.schemas.management import AccountCreate, AccountUpdate
from app.services import account_import, notifications

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
def create_account(
    payload: AccountCreate,
    background: BackgroundTasks,
    invite: bool = Query(
        False, description="Email a set-password link instead of using the password."
    ),
    db: Session = Depends(get_session),
    actor: Account = Depends(get_current_account),
):
    if payload.class_group_id is not None:
        crud.get_or_404(db, ClassGroup, payload.class_group_id)

    data = payload.model_dump(exclude={"password"})
    data["email"] = data["email"].lower()
    data["password_hash"] = hash_password(payload.password)
    account = crud.create(db, Account, data, DUPLICATE)

    if invite:
        background.add_task(
            notifications.send_invitation, account, invited_by=actor.full_name
        )
    return account


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


MAX_IMPORT_BYTES = 2 * 1024 * 1024


@router.post("/import", response_model=ImportReportOut)
async def import_accounts(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Report only. Set false to write."),
    on_existing: str = Query("skip", pattern="^(skip|update)$"),
    invite: bool = Query(
        True,
        description=(
            "Email each new account a set-password link. When on, no password "
            "is generated or shown."
        ),
    ),
    db: Session = Depends(get_session),
    actor: Account = Depends(get_current_account),
):
    """Bulk-create accounts from a CSV.

    Defaults to a dry run: the file is parsed, validated in full and reported
    on without writing anything, so every problem is visible at once rather
    than one failed upload at a time. Writing is opt-in, and happens only when
    the whole file is clean — a partially imported roll is worse than none,
    because the missing students are invisible until their response rates look
    wrong.
    """
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="That file is larger than 2 MB. Split it and import in parts.",
        )

    report = account_import.build_report(
        db, content, dry_run=dry_run, on_existing=on_existing, invite=invite
    )

    if not dry_run:
        if not report.ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "The file has problems on "
                    f"{report.errors or len(report.file_errors)} row(s). "
                    "Nothing was imported. Run it as a dry run to see them all."
                ),
            )
        created = account_import.apply(db, content, report, on_existing=on_existing)
        if invite:
            # One link each, in the background: a roll of four hundred must not
            # hold the request open, and a bounced address must not fail the
            # import that already succeeded.
            for account in created:
                background.add_task(
                    notifications.send_invitation, account, invited_by=actor.full_name
                )

    return ImportReportOut(
        dry_run=dry_run,
        file_errors=report.file_errors,
        total=len(report.rows),
        created=report.created,
        updated=report.updated,
        skipped=report.skipped,
        errors=report.errors,
        ok=report.ok,
        rows=[
            {
                "line": row.line,
                "action": row.action,
                "email": row.email,
                "name": row.name,
                "role": row.role,
                "messages": row.messages,
                # Never leak a password for a row that was only simulated as
                # existing, and never for an update.
                "generated_password": row.generated_password
                if row.action == "create"
                else None,
            }
            for row in report.rows
        ],
    )

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.catalog import ClassGroup
from app.models.enums import Role


class Account(Base, TimestampMixin):
    """Replaces `users`, `faculty_list` and `student_list`.

    Those three tables carried identical columns and differed only in
    `school_id` and `class_id`. Keeping them separate is what forced the login
    form to send an index that selected a table name, which is how
    authentication became bypassable.
    """

    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint(
            "role <> 'student' OR class_group_id IS NOT NULL",
            name="student_requires_class",
        ),
        CheckConstraint(
            "password_hash IS NOT NULL OR legacy_md5 IS NOT NULL",
            name="some_credential_present",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role", native_enum=False, length=20), index=True
    )

    # Institutional roll or staff number. Absent for admin accounts, so it is
    # nullable and unique rather than a second primary key.
    school_id: Mapped[str | None] = mapped_column(String(50), unique=True)

    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)

    # Argon2id. Nullable only while a migrated account still holds legacy_md5;
    # the check constraint above requires one of the two.
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # Carried across from the legacy tables and cleared on first successful
    # login, when the submitted password is rehashed properly.
    legacy_md5: Mapped[str | None] = mapped_column(String(32))

    class_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_group.id", ondelete="RESTRICT"), index=True
    )
    avatar: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)

    class_group: Mapped[ClassGroup | None] = relationship(lazy="joined")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def needs_password_upgrade(self) -> bool:
        return self.password_hash is None and self.legacy_md5 is not None

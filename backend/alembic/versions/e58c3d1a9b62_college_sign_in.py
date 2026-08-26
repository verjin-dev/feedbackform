"""College sign-in: link a directory account to an account here

Adds the link table only. Nothing about how anyone signs in today changes:
password sign-in keeps working, and with no OIDC configuration the feature is
off and the sign-in page does not offer it.

Revision ID: e58c3d1a9b62
Revises: d72f5b9c1e34
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e58c3d1a9b62'
down_revision: Union[str, None] = 'd72f5b9c1e34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "external_identity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("email_at_link", sa.String(length=255), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        # CASCADE: a link to a deleted account is not a link to anything, and
        # leaving it would let a recreated account id inherit somebody's
        # sign-in.
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="uq_external_identity_subject"),
        sa.UniqueConstraint("provider", "account_id", name="uq_external_identity_account"),
    )
    op.create_index(
        op.f("ix_external_identity_account_id"), "external_identity", ["account_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_external_identity_account_id"), table_name="external_identity")
    op.drop_table("external_identity")

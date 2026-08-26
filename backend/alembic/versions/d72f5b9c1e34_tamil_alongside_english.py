"""Tamil alongside English on the student-facing surface

Three additions, all nullable or defaulted, none of which change what an
existing row means:

  - question.text_ta and criterion.name_ta hold the college's own wording in
    Tamil. NULL means nobody has supplied it yet and English stands in.
  - account.language records which language a person reads the form in.

Nothing here touches a rating, a response, or anything a student submitted.

Revision ID: d72f5b9c1e34
Revises: c41d8a2e57f0
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd72f5b9c1e34'
down_revision: Union[str, None] = 'c41d8a2e57f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("question", sa.Column("text_ta", sa.Text(), nullable=True))
    op.add_column("criterion", sa.Column("name_ta", sa.String(length=255), nullable=True))

    # Defaulted rather than nullable: every account reads in some language, and
    # "unknown" would only ever be resolved to English at the point of use.
    op.add_column(
        "account",
        sa.Column(
            "language",
            sa.String(length=5),
            nullable=False,
            server_default="en",
        ),
    )


def downgrade() -> None:
    # The Tamil wording is discarded with the columns. It is the college's own
    # text and is not recoverable from anywhere else, so anyone rolling this
    # back should export the questionnaire first.
    op.drop_column("account", "language")
    op.drop_column("criterion", "name_ta")
    op.drop_column("question", "text_ta")

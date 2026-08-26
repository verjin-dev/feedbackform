"""Department-scoped questions

A question with a curriculum is asked only of students whose class carries it;
NULL keeps the existing behaviour of asking everybody. Every question that
exists when this runs becomes a core question, so the questionnaire students
see the day after the upgrade is the one they saw the day before.

Revision ID: c41d8a2e57f0
Revises: b3ba61084771
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c41d8a2e57f0'
down_revision: Union[str, None] = 'b3ba61084771'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable with no server default: NULL is the meaning, not a placeholder
    # for one, and existing rows are correct as they stand.
    op.add_column("question", sa.Column("curriculum", sa.String(length=100), nullable=True))
    op.create_index("ix_question_term_scope", "question", ["term_id", "curriculum"])


def downgrade() -> None:
    # Department questions are dropped rather than folded into the core: asking
    # one department's question of the whole college on the way back would
    # silently change what everybody is asked.
    op.execute(sa.text("DELETE FROM question WHERE curriculum IS NOT NULL"))
    op.drop_index("ix_question_term_scope", table_name="question")
    op.drop_column("question", "curriculum")

"""every conversation has a title

A conversation is created by its first message and titled after it. Conversations
without a title never got a message, because their first one was refused, so they are
deleted before the column becomes required.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM conversations WHERE title IS NULL")
    op.alter_column("conversations", "title", nullable=False)


def downgrade() -> None:
    op.alter_column("conversations", "title", nullable=True)

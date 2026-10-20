"""notes

The notes Zoomer saves for a customer through the ``save_note`` tool, e.g. wishlist
items. A note belongs to its customer and remembers the conversation and the turn it
was saved in.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "turn_id",
            sa.Uuid(),
            sa.ForeignKey("turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="confirmed", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notes_user_created", "notes", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notes_user_created", table_name="notes")
    op.drop_table("notes")

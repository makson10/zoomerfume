"""note decisions and turn security mode

A note can wait for the customer as "pending" until they confirm or reject it, and
decided_at records when they did. The transcript finds a conversation's notes by
conversation_id, so it gets an index. Each turn stores the prompt-injection defenses it ran
with. Turns from before the defenses existed ran without any, so they are stored as
"vulnerable".

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "turns",
        sa.Column(
            "security_mode", sa.String(length=32), server_default="vulnerable", nullable=False
        ),
    )
    op.alter_column("turns", "security_mode", server_default=None)
    op.add_column("notes", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_notes_conversation_id", "notes", ["conversation_id"])


def downgrade() -> None:
    op.execute("DELETE FROM notes WHERE status <> 'confirmed'")
    op.drop_index("ix_notes_conversation_id", table_name="notes")
    op.drop_column("notes", "decided_at")
    op.drop_column("turns", "security_mode")

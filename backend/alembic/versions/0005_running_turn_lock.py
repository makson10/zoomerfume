"""one running turn per conversation

A partial unique index allows only one ``running`` turn per conversation, so a message
sent while Zoomer is still answering in the same chat is refused. Turns that a stopped
server left ``running`` are marked ``failed`` first, so the index can be built.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE turns SET status = 'failed', finished_at = now() WHERE status = 'running'")
    op.create_index(
        "ux_turns_one_running",
        "turns",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("ux_turns_one_running", table_name="turns")

"""agent history tables

Agent history moves from a SQLite file to Postgres. ``agent_sessions`` and
``agent_messages`` match the tables of the Agents SDK's ``SQLAlchemySession``, which
reads and writes them but doesn't create them. History in the old SQLite file is not
copied over.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sdk_timestamp(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.TIMESTAMP(timezone=False),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.String(), primary_key=True),
        _sdk_timestamp("created_at"),
        _sdk_timestamp("updated_at"),
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("agent_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_data", sa.Text(), nullable=False),
        _sdk_timestamp("created_at"),
    )
    op.create_index(
        "idx_agent_messages_session_time", "agent_messages", ["session_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_agent_messages_session_time", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")

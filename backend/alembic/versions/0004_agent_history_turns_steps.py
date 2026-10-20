"""agent history, turns and tool_steps tables

Agent history moves from a SQLite file to Postgres. ``agent_sessions`` and
``agent_messages`` match the tables of the Agents SDK's ``SQLAlchemySession``, which
reads and writes them but doesn't create them. History in the old SQLite file is not
copied over.

Every chat message now belongs to a row in ``turns``. Older messages have no turn, so
their ``turn_id`` is cleared before it becomes a foreign key. ``messages.meta`` held only
a "degraded" flag, which ``turns.status`` replaces.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

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

    op.create_table(
        "turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_turns_conversation_id", "turns", ["conversation_id"])
    op.create_table(
        "tool_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "turn_id",
            sa.Uuid(),
            sa.ForeignKey("turns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("args", postgresql.JSONB(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("record_ids", postgresql.ARRAY(sa.String(length=8)), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tool_steps_turn_id", "tool_steps", ["turn_id"])

    op.drop_column("messages", "meta")
    op.execute("UPDATE messages SET turn_id = NULL")
    op.alter_column("messages", "turn_id", type_=sa.Uuid(), postgresql_using="turn_id::uuid")
    op.create_foreign_key(
        "fk_messages_turn_id", "messages", "turns", ["turn_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_turn_id", "messages", type_="foreignkey")
    op.alter_column(
        "messages", "turn_id", type_=sa.String(length=64), postgresql_using="turn_id::text"
    )
    op.add_column("messages", sa.Column("meta", postgresql.JSONB(), nullable=True))

    op.drop_index("ix_tool_steps_turn_id", table_name="tool_steps")
    op.drop_table("tool_steps")
    op.drop_index("ix_turns_conversation_id", table_name="turns")
    op.drop_table("turns")

    op.drop_index("idx_agent_messages_session_time", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")

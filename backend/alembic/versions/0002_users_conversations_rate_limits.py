"""users, conversations and rate_limits tables

Messages now belong to a conversation. Rows logged before sign-in existed have no
owner and are local dev data only, so the upgrade deletes them before it turns
``messages.conversation_id`` into a foreign key.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("phone", sa.String(length=16), nullable=False, unique=True),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )

    op.execute("DELETE FROM messages")
    op.alter_column(
        "messages",
        "conversation_id",
        type_=sa.Uuid(),
        postgresql_using="conversation_id::uuid",
    )
    op.create_foreign_key(
        "fk_messages_conversation_id",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_conversation_id", "messages", type_="foreignkey")
    op.alter_column(
        "messages",
        "conversation_id",
        type_=sa.String(length=64),
        postgresql_using="conversation_id::text",
    )
    op.drop_table("rate_limits")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("users")

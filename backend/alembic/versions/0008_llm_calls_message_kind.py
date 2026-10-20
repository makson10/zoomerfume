"""llm_calls and messages.kind

One row per model call with its token usage and cost: the chat calls of each turn and
the embedding calls of searches and ingest runs. Messages get a kind, so a chat command
such as /cost and its reply are told apart from the chat itself.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "turn_id",
            sa.Uuid(),
            sa.ForeignKey("turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=9), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_llm_calls_turn_id", "llm_calls", ["turn_id"])
    op.add_column(
        "messages",
        sa.Column("kind", sa.String(length=16), server_default="chat", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("messages", "kind")
    op.drop_index("ix_llm_calls_turn_id", table_name="llm_calls")
    op.drop_table("llm_calls")

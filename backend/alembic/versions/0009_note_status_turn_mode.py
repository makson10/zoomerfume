"""turn security mode

Each turn stores the prompt-injection defenses it ran with. Turns from before the
defenses existed ran without any, so they are stored as "vulnerable".

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


def downgrade() -> None:
    op.drop_column("turns", "security_mode")

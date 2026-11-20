"""pg_trgm extension

The similar perfume search finds the product a customer names by trigram word similarity,
so a part of the title or a small typo still matches.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

"""Declarative base shared by every ORM model and by Alembic's autogenerate.

Kept in its own tiny module (no engine import) so ``alembic/env.py`` can import
``Base.metadata`` without pulling in the runtime engine, and so model modules
never create an import cycle through the engine.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all tables."""

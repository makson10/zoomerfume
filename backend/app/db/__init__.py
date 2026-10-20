"""Postgres persistence (async SQLAlchemy): the engine, the ORM models and the message log.

The schema is owned by Alembic and migrated on container start. Agent history lives in
the ``agent_sessions`` and ``agent_messages`` tables, which the Agents SDK reads and writes
itself, so they have no ORM models here.
"""

"""Postgres persistence (async SQLAlchemy).

Currently a side-write message log: every chat exchange is recorded as a user
row and an assistant row (:class:`~app.db.models.Message`). Writes are fail-open —
a database outage logs and returns rather than ever delaying or breaking a chat
turn. The schema is owned by Alembic (migrated on container start).
"""

#!/bin/sh
# Container entrypoint: bring the database schema up to head, then hand off
# to the app command (CMD in prod, the --reload override in dev). Fail hard if
# the migration fails — the app must never run against a stale schema.
set -e

echo "[entrypoint] running alembic upgrade head…"
alembic upgrade head

exec "$@"

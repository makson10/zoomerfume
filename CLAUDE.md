# CLAUDE.md

This file gives Claude Code the project context and operating rules for the
Zoomerfume repository. Read it before planning, editing, or testing code.

## Project Context

Zoomerfume is a fictional Ukrainian online perfume shop (prices in UAH). This
repository is its AI shop assistant, **Zoomer**: a chat bot that recommends
perfumes, compares products, answers shop questions and gives general perfume
advice. The goal is a *grounded* assistant: answers about the shop must come from a
knowledge base the model searches through tools, with citations, never from the
model's memory.

Current state: a non-streaming chat API with Zoomer and no tools yet. Zoomer can
talk about perfume in general but can't look up the shop's catalog, prices or
policies, and says so.

The repository root is a single git repo. Backend code lives in `backend/`; Docker
files, `.env.example` and docs live at the root.

## Request Flow

```
client ── POST /api/chat ──► api (FastAPI, app/api/chat.py)
                               │
                               ├── TurnRunner.run() ──► OpenAI Responses API (CHAT_MODEL)
                               ├── history ───────────► SQLite    data/agents/sessions.db
                               └── message log ───────► Postgres  messages table (fail-open)

app startup:        ping Postgres + Qdrant (a failure is logged, never fatal)
container startup:  alembic upgrade head, then uvicorn
```

Qdrant is wired in (client, startup ping, Compose service) but nothing reads or
writes collections yet.

## Repository Layout

- `backend/app/`: the FastAPI application
  - `api/`: HTTP routes (`health.py`, `chat.py`) and route dependencies (`deps.py`)
  - `agent/`: Zoomer's runtime, system prompt and per-turn context
  - `core/`: settings, logging setup
  - `db/`: SQLAlchemy engine, models, fail-open write guard, message log
  - `middleware/`: per-request logging context
  - `services/`: OpenAI and Qdrant client constructors
- `backend/alembic/`: database migrations (`versions/0001_messages.py`, ...)
- `backend/tests/`: pytest unit tests and test fakes
- `backend/scripts/entrypoint.sh`: container entrypoint
- `backend/pyproject.toml`, `backend/uv.lock`: the uv project (Python 3.12)
- `.github/workflows/ci.yml`: the CI workflow
- Root: `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`,
  `.env.example`, `README.md`

## Entry Points

- ASGI app: the `app.main:create_app` factory. The image runs it with
  `uvicorn --factory` (`--loop uvloop --no-access-log`); the dev override swaps in
  `--reload`.
- Container start: `backend/scripts/entrypoint.sh` runs `alembic upgrade head`,
  then `exec`s the command. A failed migration stops the container.
- HTTP API:
  - `GET /health` → `{"status": "ok"}` (liveness only)
  - `POST /api/chat` `{session_id, message}` → `{reply}`; 422 on invalid input
  - `/docs` and `/redoc` only when `DEBUG=true`

## Current Stack

- Runtime: Python 3.12, managed with uv. The Docker image installs from
  `uv.lock` with `uv sync --frozen`.
- Web: FastAPI + uvicorn, pydantic v2, pydantic-settings.
- LLM: OpenAI Agents SDK (`openai-agents`) on the OpenAI Responses API. Chat model
  `gpt-6-luna`, which rejects `temperature`, so the agent uses low reasoning effort
  instead.
- Persistence: Postgres 17 through async SQLAlchemy 2 + asyncpg. Alembic
  migrations are hand-written. Agent conversation history lives in a SQLite file.
- Vector store: Qdrant (server and `qdrant-client`, both v1.19).
- Logging: structlog on top of stdlib `logging`. JSON lines by default, colored
  console output when `DEBUG=true`.
- Lint/format: ruff (line length 100, rules `E`, `F`, `I`, `UP`).
- Runtime environment: Docker Compose with `api`, `postgres` and `qdrant`.

## Architecture Notes

A chat turn goes through these steps:

1. `POST /api/chat` (`app/api/chat.py`) validates `{session_id, message}`. Both
   fields are stripped; `message` is 1–4000 characters.
2. The route gets the `TurnRunner` (`app/agent/runtime.py`) through the
   `get_turn_runner` dependency (`app/api/deps.py`). `TurnRunner.run()` builds a
   `TurnContext` and calls `Runner.run` with the runner's `Agent`.
3. The agent's instructions are the static `AGENT_INSTRUCTIONS`
   (`app/agent/prompts.py`) plus the current date and time in UTC, recomputed on
   every run.
4. History comes from `RetentionSQLiteSession` at `data/agents/sessions.db`
   (relative to the working directory). The model input is capped two ways, and
   neither deletes stored rows:
   - by age: `HISTORY_RETENTION_DAYS`, in `get_items()`
   - by count: the last `HISTORY_WINDOW_TURNS` user turns, in `window_history()`
   
   Both cut only on turn boundaries, so a tool call is never separated from its
   output.
5. Every request carries `prompt_cache_key = session:<session_id>`, and the run is
   capped at `AGENT_MAX_TURNS` agent-loop iterations.
6. Any runtime error, or an empty answer, becomes `FALLBACK_TEXT`, and the turn is
   marked `degraded`. The endpoint still answers 200.
7. When `MESSAGE_LOG_ENABLED=true`, `record_turn_messages()` writes the user row
   and the assistant row to the `messages` table through `pg_guard`.

**Message log writes are fail-open.** `pg_guard` (`app/db/guard.py`) bounds the
write to 5 seconds, and logs and swallows any error. A database problem must never
break a chat turn.

**Startup and shutdown.** `create_app(settings=None)` (`app/main.py`) loads the
settings (or takes the ones passed in), sets up logging and stores the settings on
`app.state`. Nothing runs at import time. The lifespan creates the OpenAI and
Qdrant clients and the SQLAlchemy engine, points the Agents SDK at the app's own
`AsyncOpenAI` client through `set_default_openai_client`, and stores one
`TurnRunner` on `app.state`. It then pings Postgres and Qdrant; if either is down,
it logs the error and keeps starting. Shutdown closes the clients and disposes the
engine. `GET /health` is a liveness check that always returns `{"status": "ok"}`.

**Dependencies.** Code gets settings and clients passed in; no module reads
settings at import time. Routes get lifespan objects through FastAPI dependencies
in `app/api/deps.py`, which read `app.state`. Add a new dependency there when a
route first needs a new shared object.

**Migrations.** The container entrypoint runs `alembic upgrade head` before it
starts uvicorn. `alembic/env.py` reads the DSN from the app settings, so the
database URL is defined in exactly one place.

## Tests

Unit tests live in `backend/tests/` and run with pytest (`asyncio_mode = "auto"`).
They never call OpenAI, Postgres or Qdrant:

- `conftest.py` builds `Settings` in code with `_env_file=None`, so a real key in
  `.env` is never read.
- The `client` fixture overrides `get_turn_runner` with `FakeTurnRunner`
  (`tests/fakes.py`) and uses `TestClient` without `with`, so the lifespan never
  runs.
- Runtime tests replace `Runner.run` and run in a temporary directory, so no
  SQLite file is created in `backend/`.

Keep tests few and focused: the happy path plus the errors that matter. Replace
external services with fakes at the boundary instead of starting them.

CI (`.github/workflows/ci.yml`) runs on pull requests and pushes to `dev` and
`main`. Job `backend` runs `uv sync --frozen`, `ruff check`, `ruff format --check`
and `pytest` in `backend/`. Job `docker` builds the image.

## Configuration

The app reads environment variables only, through `app/core/config.py`. For local
runs, pydantic-settings also reads `../.env` and `./.env`, so one `.env` at the
repo root works both for Compose and for a run from `backend/`. Real environment
variables take precedence over `.env` values.

- `.env.example` is the committed template. `.env` holds real secrets and is
  git-ignored.
- Compose passes the root `.env` into the `api` container (`env_file`). Postgres
  credentials also have defaults in `docker-compose.yml`.
- Inside Compose, services reach each other by service name (`postgres`,
  `qdrant`). A backend run on the host must point `DATABASE_URL` and `QDRANT_URL`
  at `localhost` (see Common Commands).
- After editing `.env`, recreate the container with `docker compose up -d api`.
  `docker compose restart` reuses the old container config and does not re-read
  `.env`.

## Common Commands

Run Compose commands from the repo root. Run uv, ruff and alembic from `backend/`.

Full stack (the dev override adds `--reload`, file sync and host ports for
Postgres and Qdrant):

```bash
cp .env.example .env               # first time only; set OPENAI_API_KEY
docker compose up --build          # add --watch to sync backend/app changes live
docker compose logs -f api
docker compose -f docker-compose.yml up -d --build   # without the dev override
```

`--watch` syncs only `backend/app/`. Changes to `pyproject.toml` or `uv.lock`
trigger a rebuild. New migrations need `docker compose up --build`, because the
entrypoint applies them when the container starts.

Smoke checks:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"session_id": "demo", "message": "hi"}'
docker compose exec postgres psql -U zoomer -d zoomerfume \
  -c 'select role, left(content, 60), created_at from messages order by id desc limit 4'
```

Backend on the host, with Postgres and Qdrant in Docker:

```bash
docker compose up -d postgres qdrant
cd backend
uv sync
export DATABASE_URL=postgresql+asyncpg://zoomer:zoomer@localhost:5432/zoomerfume
export QDRANT_URL=http://localhost:6333
uv run alembic upgrade head
uv run uvicorn --factory app.main:create_app --reload
```

Lint, format, tests, dependencies and migrations:

```bash
uv run ruff check .
uv run ruff format .
uv run pytest
uv add <package>                   # updates pyproject.toml and uv.lock
uv add --dev <package>
uv run alembic revision -m "<description>" --rev-id 0002   # then hand-write the body
uv run alembic upgrade head
uv run alembic downgrade -1
```

`/docs` (Swagger UI) is available only when `DEBUG=true`.

If the user asks Claude to run the project, the API or the full stack, Claude
should start the required processes in its own background terminal when possible.
Do not stop at listing commands. Report the command, working directory, URL/port,
and any missing dependency or config that prevents startup: Docker not running, no
`OPENAI_API_KEY`, a port already in use, and so on.

## Notes

- Verify changes with `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest` and the smoke checks above.
- In `README.md`, write each paragraph, list item and blockquote as one line. Don't
  hard-wrap prose at a fixed width; editors and GitHub wrap it. Code blocks, tables
  and the ASCII diagrams keep their own line breaks.
- Agent history lives in the container filesystem (`/app/data/agents/sessions.db`),
  not on a volume. Recreating the `api` container (a rebuild, `docker compose down`)
  starts every conversation fresh; the `messages` table in Postgres keeps the log.
- Two HTTP client libraries are installed: `openai` 3.x (and so the Agents SDK)
  uses `httpx2`/`httpcore2`, while `qdrant-client` uses `httpx` 0.28. Their loggers
  are quieted separately in `app/core/logging.py`. OpenAI failures surface as
  `openai.*` exceptions, not `httpx` ones.
- Every chat check calls OpenAI and costs a little. Keep manual checks short.

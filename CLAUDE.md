# CLAUDE.md

This file gives Claude Code the project context and operating rules for the Zoomerfume repository. Read it before planning, editing, or testing code.

## Project Context

Zoomerfume is a fictional Ukrainian online perfume shop (prices in UAH). This repository is its AI shop assistant, **Zoomer**: a chat bot that recommends perfumes, compares products, answers shop questions and gives general perfume advice. The goal is a *grounded* assistant: answers about the shop must come from a knowledge base the model searches through tools, with citations, never from the model's memory.

Current state: a web chat with Zoomer on top of a non-streaming chat API, with no tools yet. Customers sign in with a phone number and keep several conversations each. Zoomer can talk about perfume in general but can't look up the shop's catalog, prices or policies, and says so.

The repository root is a single git repo. Backend code lives in `backend/` and the web chat in `frontend/`; Docker files, `.env.example` and docs live at the root.

## Request Flow

```
browser ── GET / ─────────────────────► api: static files from /app/static (the built frontend)
browser ── /api/auth/*, /api/me ──────► api (app/api/auth.py) ──► Postgres users, rate_limits
browser ── /api/conversations/* ──────► api (app/api/conversations.py) ──► Postgres conversations, messages
browser ── POST /api/chat ────────────► api (FastAPI, app/api/chat.py)
                                          │
                                          ├── session cookie ──► user, rate limit, conversation owner check
                                          ├── TurnRunner.run() ──► OpenAI Responses API (CHAT_MODEL)
                                          ├── history ───────────► SQLite    data/agents/sessions.db
                                          └── message log ───────► Postgres  messages table (fail-open)

app startup:        ping Postgres + Qdrant (a failure is logged, never fatal)
container startup:  alembic upgrade head, then uvicorn
```

Qdrant is wired in (client, startup ping, Compose service) but nothing reads or writes collections yet.

## Repository Layout

- `backend/app/`: the FastAPI application
  - `api/`: HTTP routes (`health.py`, `auth.py`, `conversations.py`, `chat.py`), route dependencies (`deps.py`), the JSON error body (`errors.py`) and the web chat mount (`spa.py`)
  - `agent/`: Zoomer's runtime, system prompt and per-turn context
  - `core/`: settings, logging setup, phone and name validation (`validators.py`)
  - `db/`: SQLAlchemy engine, models, fail-open write guard, message log
  - `middleware/`: per-request logging context
  - `services/`: OpenAI and Qdrant client constructors, users and the session cookie (`auth.py`), conversations (`conversations.py`), rate limits (`rate_limit.py`)
- `backend/alembic/`: database migrations (`versions/0001_messages.py`, ...)
- `backend/tests/`: pytest unit tests and test fakes
- `backend/scripts/entrypoint.sh`: container entrypoint
- `backend/pyproject.toml`, `backend/uv.lock`: the uv project (Python 3.12)
- `frontend/`: the web chat (Vite + React + TypeScript + Mantine)
  - `src/App.tsx`: picks the page: a loader, the sign-in chat or the chat page
  - `src/api/`: the fetch wrapper (`client.ts`) and one module per API area (`auth.ts`, `conversations.ts`, `chat.ts`)
  - `src/components/`: `ChatPage` (navbar + chat), `SignInFlow`, `ConversationList`, `ChatPanel` (message list + composer), `Header`, `MessageList`, `MessageBubble`, `Composer`
  - `src/hooks/`: `useSession` (the signed-in user) and `useChat` (conversations and the open chat)
  - `src/theme.ts`: the Mantine theme
  - `public/logo.svg`: the logo, also used as the favicon
- `.github/workflows/ci.yml`: the CI workflow
- Root: `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `.env.example`, `README.md`

## Entry Points

- ASGI app: the `app.main:create_app` factory. The image runs it with `uvicorn --factory` (`--loop uvloop --no-access-log`); the dev override swaps in `--reload`.
- Container start: `backend/scripts/entrypoint.sh` runs `alembic upgrade head`, then `exec`s the command. A failed migration stops the container.
- HTTP API:
  - `GET /health` → `{"status": "ok"}` (liveness only)
  - `POST /api/auth/phone` `{phone}` → `{status: "known", user, message}` with the session cookie, or `{status: "need_name", phone, message}`; 422 `INVALID_PHONE`
  - `POST /api/auth/create` `{phone, name}` → 201 `{user, message}` with the session cookie; 422 `INVALID_PHONE` or `INVALID_NAME`
  - `POST /api/auth/logout` → 204, the session is cleared
  - `GET /api/me` → `{id, name, phone_masked}`
  - `GET /api/conversations` → `[{id, title}]`, the most recently active first; `POST /api/conversations` → 201 `{id, title: null}`
  - `GET /api/conversations/{id}/messages` → `[{id, role, content}]`, oldest first
  - `POST /api/chat` `{conversation_id, message}` → `{reply}`; 422 on invalid input
  - Every `/api/*` route except `/api/auth/*` needs a signed-in user (401 otherwise). Someone else's conversation is a 404. Over a rate limit is a 429 with `Retry-After`. These errors have the body `{"error": {"code", "message"}}`; the `message` is written for the customer.
  - `GET /openapi.json` is served in every mode, so API types can be generated from it
  - `/docs` and `/redoc` only when `DEBUG=true`
- Web chat: `GET /` and the files next to it (`/assets/*`, `/logo.svg`), when the image has a frontend build. Any other path gets FastAPI's JSON 404.

## Current Stack

- Runtime: Python 3.12, managed with uv. The Docker image installs from `uv.lock` with `uv sync --frozen`.
- Web: FastAPI + uvicorn, pydantic v2, pydantic-settings.
- LLM: OpenAI Agents SDK (`openai-agents`) on the OpenAI Responses API. Chat model `gpt-6-luna`, which rejects `temperature`, so the agent uses low reasoning effort instead.
- Persistence: Postgres 17 through async SQLAlchemy 2 + asyncpg. Alembic migrations are hand-written. Agent conversation history lives in a SQLite file.
- Vector store: Qdrant (server and `qdrant-client`, both v1.19).
- Logging: structlog on top of stdlib `logging`. JSON lines by default, colored console output when `DEBUG=true`.
- Frontend: npm (CI and the Docker image use Node.js 22), Vite 8, React 19, TypeScript 6.0, Mantine 9, `react-markdown` with `remark-gfm`, Tabler icons.
- Lint/format: ruff for the backend (line length 100, rules `E`, `F`, `I`, `UP`); oxlint and Prettier for the frontend (no semicolons, single quotes).
- Runtime environment: Docker Compose with `api`, `postgres` and `qdrant`.

## Architecture Notes

A chat turn goes through these steps:

1. `POST /api/chat` (`app/api/chat.py`) validates `{conversation_id, message}`. `message` is stripped and 1–4000 characters.
2. Dependencies run first: `get_current_user` reads the user from the session cookie (401), and `limit_chat` counts the message against the user's rate limit (429). The route then loads the conversation only if it belongs to the user (404), titles it after its first message and moves it to the top of the list.
3. The route gets the `TurnRunner` (`app/agent/runtime.py`) through the `get_turn_runner` dependency (`app/api/deps.py`). `TurnRunner.run()` builds a `TurnContext` and calls `Runner.run` with the runner's `Agent`.
4. The agent's instructions are the static `AGENT_INSTRUCTIONS` (`app/agent/prompts.py`) plus the current date and time in UTC and the customer's name, recomputed on every run.
5. History comes from `RetentionSQLiteSession` at `data/agents/sessions.db` (relative to the working directory), with the conversation id as the session id. The model input is capped two ways, and neither deletes stored rows:
   - by age: `HISTORY_RETENTION_DAYS`, in `get_items()`
   - by count: the last `HISTORY_WINDOW_TURNS` user turns, in `window_history()`

   Both cut only on turn boundaries, so a tool call is never separated from its output.
6. Every request carries `prompt_cache_key = conversation:<conversation_id>`, and the run is capped at `AGENT_MAX_TURNS` agent-loop iterations.
7. Any runtime error, or an empty answer, becomes `FALLBACK_TEXT`, and the turn is marked `degraded`. The endpoint still answers 200.
8. When `MESSAGE_LOG_ENABLED=true`, `record_turn_messages()` writes the user row and the assistant row to the `messages` table through `pg_guard`.

**Message log writes are fail-open.** `pg_guard` (`app/db/guard.py`) bounds the write to 5 seconds, and logs and swallows any error. A database problem must never break a chat turn. The web chat reads transcripts from this table, so with `MESSAGE_LOG_ENABLED=false` reopened conversations look empty.

**Sign-in.** A scripted flow in code, never the model: `/api/auth/phone` signs in a known number or answers `need_name`, then `/api/auth/create` creates the account. There is no SMS code; the shop is fictional. `validate_phone` (`phonenumbers`, `PHONE_DEFAULT_REGION` for numbers without a country code) stores numbers as E.164, and `validate_name` allows 2–40 letters, spaces, hyphens and apostrophes, because the name goes into the instructions. `UserStore.get_or_create` is one upsert, so a phone always maps to one account. Starlette's `SessionMiddleware` keeps only `user_id` in the `zoomerfume_session` cookie, signed with `SESSION_SECRET` (HttpOnly, SameSite=Lax, 30 days). The cookie holds all session state, so any API replica can serve any request.

**Rate limits.** `RateLimiter.hit()` (`app/services/rate_limit.py`) counts requests per key in fixed one-minute windows in the `rate_limits` table, with one atomic `INSERT … ON CONFLICT DO UPDATE … RETURNING count`. Keys are `chat:user:<id>` (`RATE_LIMIT_CHAT_PER_MIN`, checked in `limit_chat`) and `auth:ip:<client address>` (`RATE_LIMIT_AUTH_PER_MIN`, on `/api/auth/phone` and `/api/auth/create`). When a key opens a new window, rows older than a day are deleted. Postgres holds the counters, so the limits stay correct with several replicas.

**Data access.** Routes reach Postgres through small stores (`UserStore`, `ConversationStore`, `RateLimiter`), each built per request on the `get_db` session. Tests replace the stores, not the database.

**Startup and shutdown.** `create_app(settings=None)` (`app/main.py`) loads the settings (or takes the ones passed in), sets up logging and stores the settings on `app.state`. Nothing runs at import time. After the routers it calls `mount_web_chat()` (`app/api/spa.py`), which mounts the frontend build at `/` only if `backend/static/index.html` exists (`/app/static` in the image). Without a build, as in unit tests or a backend run on the host, the app serves the API only. The lifespan creates the OpenAI and Qdrant clients and the SQLAlchemy engine, points the Agents SDK at the app's own `AsyncOpenAI` client through `set_default_openai_client`, and stores the session factory (`sessionmaker`) and one `TurnRunner` on `app.state`. It then pings Postgres and Qdrant; if either is down, it logs the error and keeps starting, and sign-in and chat fail until Postgres is back. Shutdown closes the clients and disposes the engine. `GET /health` is a liveness check that always returns `{"status": "ok"}`.

**Dependencies.** Code gets settings and clients passed in; no module reads settings at import time. Routes get lifespan objects through FastAPI dependencies in `app/api/deps.py`, which read `app.state`. Add a new dependency there when a route first needs a new shared object.

**Migrations.** The container entrypoint runs `alembic upgrade head` before it starts uvicorn. `alembic/env.py` reads the DSN from the app settings, so the database URL is defined in exactly one place.

**Web chat.** A single page with no router and no state library. On load, `useSession` calls `/api/me`; a 401 shows `SignInFlow`, where Zoomer asks for the phone and then the name as chat bubbles. Zoomer's first question is in the frontend, and every later line comes from the API's `message`. When signed in, `ChatPage` remounts per user. `useChat` loads the conversation list, opens the most recent conversation with its transcript, and keeps the rest in React state. "New chat" only clears the view: the first message creates the conversation, so the list never fills with empty chats. Sending and switching chats are blocked while a request is pending. API errors with a code show their `message` (a rate limit, for example); other failures show a generic line. All requests go through `src/api/client.ts`. Assistant replies render as Markdown (GFM tables included, raw HTML is not rendered); user messages render as plain text. The color scheme follows the system, and the header toggle overrides it. Keep the UI minimal and functional: stock Mantine components and the theme in `theme.ts`. In development the Vite dev server proxies `/api` to `localhost:8000`, so the browser never needs CORS. In the image, the first Docker stage builds the frontend and the runtime stage copies `frontend/dist` to `/app/static`.

## Tests

Unit tests live in `backend/tests/` and run with pytest (`asyncio_mode = "auto"`). They never call OpenAI, Postgres or Qdrant:

- `conftest.py` builds `Settings` in code with `_env_file=None`, so a real key in `.env` is never read.
- The `client` fixture overrides `get_turn_runner`, `get_user_store`, `get_conversation_store` and `get_rate_limiter` with in-memory fakes from `tests/fakes.py`, and uses `TestClient` without `with`, so the lifespan never runs and nothing touches Postgres. The client keeps cookies, so the `user` fixture signs in through `/api/auth/phone` like a browser.
- The fakes don't run SQL. The upserts in `UserStore` and `RateLimiter` are checked against a real database in the smoke checks.
- Runtime tests replace `Runner.run` and run in a temporary directory, so no SQLite file is created in `backend/`.
- Web chat tests mount a tiny fake build from a temporary directory.

Keep tests few and focused: the happy path plus the errors that matter. Replace external services with fakes at the boundary instead of starting them. The frontend has no test suite; it is checked by lint, formatting and the type-checked build.

CI (`.github/workflows/ci.yml`) runs on pull requests and pushes to `dev` and `main`. Job `backend` runs `uv sync --frozen`, `ruff check`, `ruff format --check` and `pytest` in `backend/`. Job `frontend` runs `npm ci`, `npm run lint`, `npm run format:check` and `npm run build` in `frontend/`. Job `docker` builds the image with Buildx and caches its layers in the GitHub Actions cache.

## Configuration

The app reads environment variables only, through `app/core/config.py`. For local runs, pydantic-settings also reads `../.env` and `./.env`, so one `.env` at the repo root works both for Compose and for a run from `backend/`. Real environment variables take precedence over `.env` values.

- `.env.example` is the committed template. `.env` holds real secrets and is git-ignored.
- `SESSION_SECRET` is required and must be at least 32 characters (`openssl rand -hex 32`). Changing it signs everyone out.
- Compose passes the root `.env` into the `api` container (`env_file`). Postgres credentials also have defaults in `docker-compose.yml`.
- Inside Compose, services reach each other by service name (`postgres`, `qdrant`). A backend run on the host must point `DATABASE_URL` and `QDRANT_URL` at `localhost` (see Common Commands).
- After editing `.env`, recreate the container with `docker compose up -d api`. `docker compose restart` reuses the old container config and does not re-read `.env`.

The frontend has no configuration of its own. It calls the API on the same origin.

## Common Commands

Run Compose commands from the repo root. Run uv, ruff and alembic from `backend/`, and npm from `frontend/`.

Full stack (the dev override adds `--reload`, file sync and host ports for Postgres and Qdrant). The web chat is at http://localhost:8000:

```bash
cp .env.example .env               # first time only; set OPENAI_API_KEY and SESSION_SECRET
docker compose up --build          # add --watch to sync backend/app changes live
docker compose logs -f api
docker compose -f docker-compose.yml up -d --build   # without the dev override
```

`--watch` syncs only `backend/app/`. Changes to `pyproject.toml` or `uv.lock` trigger a rebuild. Frontend changes need `docker compose up --build`, or use the Vite dev server below. New migrations need `docker compose up --build`, because the entrypoint applies them when the container starts.

Smoke checks:

```bash
curl localhost:8000/health
curl -s localhost:8000/ | grep '<title>'    # the built web chat
# sign in (a cookie jar keeps the session), start a conversation, chat
curl -c jar -b jar -X POST localhost:8000/api/auth/phone \
  -H 'content-type: application/json' -d '{"phone": "050 111 22 33"}'
curl -c jar -b jar -X POST localhost:8000/api/auth/create \
  -H 'content-type: application/json' -d '{"phone": "050 111 22 33", "name": "Mary"}'
curl -b jar -X POST localhost:8000/api/conversations          # → {"id": "<uuid>", ...}
curl -b jar -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' -d '{"conversation_id": "<uuid>", "message": "hi"}'
docker compose exec postgres psql -U zoomer -d zoomerfume \
  -c 'select role, left(content, 60), created_at from messages order by id desc limit 4'
```

To check the chat rate limit without 20 model calls, run the `api` service with a lower `RATE_LIMIT_CHAT_PER_MIN` (an extra Compose file with `environment:` works, since `.env` is passed through `env_file`). Sign-in limits cost nothing to check: 11 invalid `/api/auth/phone` calls in one minute get a 429.

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

Frontend (needs the API on port 8000, from Compose or uvicorn):

```bash
cd frontend
npm ci
npm run dev                        # http://localhost:5173, proxies /api to localhost:8000
npm run lint                       # oxlint
npm run format                     # Prettier; format:check only checks
npm run build                      # tsc -b, then vite build into dist/
npm install <package>              # updates package.json and package-lock.json
```

`/docs` (Swagger UI) is available only when `DEBUG=true`. `/openapi.json` is always available.

If the user asks Claude to run the project, the API or the full stack, Claude should start the required processes in its own background terminal when possible. Do not stop at listing commands. Report the command, working directory, URL/port, and any missing dependency or config that prevents startup: Docker not running, no `OPENAI_API_KEY`, a port already in use, and so on.

## Notes

- Verify backend changes with `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` and the smoke checks above. Verify frontend changes with `npm run lint`, `npm run format:check`, `npm run build` and a look at the page.
- In `README.md` and `CLAUDE.md`, write each paragraph, list item and blockquote as one line. Don't hard-wrap prose at a fixed width; editors and GitHub wrap it. Code blocks, tables and the ASCII diagrams keep their own line breaks.
- Agent history lives in the container filesystem (`/app/data/agents/sessions.db`), not on a volume. Recreating the `api` container (a rebuild, `docker compose down`) makes Zoomer forget every conversation, while the web chat still shows their transcripts from the `messages` table.
- Localhost cookies are shared between ports, so the Vite dev server (`:5173`) and the API (`:8000`) share the `zoomerfume_session` cookie. The cookie has its own name so it doesn't clash with other local apps.
- Two HTTP client libraries are installed: `openai` 3.x (and so the Agents SDK) uses `httpx2`/`httpcore2`, while `qdrant-client` uses `httpx` 0.28. Their loggers are quieted separately in `app/core/logging.py`. OpenAI failures surface as `openai.*` exceptions, not `httpx` ones.
- TypeScript stays on 6.0, the version the Vite template pins.
- The production build warns that the JS bundle is over 500 kB (Mantine, Markdown and icons). It is a single local page, so there is no code splitting yet.
- Every chat check calls OpenAI and costs a little. Keep manual checks short.

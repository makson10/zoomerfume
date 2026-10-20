# CLAUDE.md

This file gives Claude Code the project context and operating rules for the Zoomerfume repository. Read it before planning, editing, or testing code.

## Project Context

Zoomerfume is a fictional Ukrainian online perfume shop (prices in UAH). This repository is its AI shop assistant, **Zoomer**: a chat bot that recommends perfumes, compares products, answers shop questions and gives general perfume advice. The goal is a *grounded* assistant: answers about the shop must come from a knowledge base the model searches through tools, with citations, never from the model's memory.

Current state: a web chat with Zoomer on top of a streaming chat API (server-sent events). Customers sign in with a phone number and keep several conversations each. Replies stream in token by token, and the customer can stop one halfway. The knowledge base (`backend/corpus/`, 96 records) is chunked, embedded and stored in Qdrant by a command-line ingest. Zoomer answers shop questions through two tools, `search_kb` and `open_record`, and cites the records it used as `[KB-042]`; general perfume questions need no tools. The web chat shows citations as chips that open the full record, a step log under each answer and the tool schemas.

The repository root is a single git repo. Backend code lives in `backend/` and the web chat in `frontend/`; Docker files, `.env.example` and docs live at the root.

## Request Flow

```
browser ── GET / ─────────────────────► api: static files from /app/static (the built frontend)
browser ── /api/auth/*, /api/me ──────► api (app/api/auth.py) ──► Postgres users, rate_limits
browser ── /api/conversations/* ──────► api (app/api/conversations.py) ──► Postgres conversations, messages, turns, tool_steps
browser ── /api/records/{id} ─────────► api (app/api/records.py) ──► Postgres kb_records
browser ── /api/tools/schema ─────────► api (app/api/tools.py): the tool objects' JSON schemas
browser ── POST /api/chat/stream (SSE) ► api (FastAPI, app/api/chat.py); POST /api/chat: same turn, one JSON reply
                                          │
                                          ├── session cookie ──► user, rate limit, conversation owner check
                                          ├── TurnStore ─────────► Postgres  turns (one running per conversation), tool_steps
                                          ├── TurnRunner.stream() ► OpenAI Responses API (CHAT_MODEL), streamed
                                          │     ├── search_kb ────► OpenAI embeddings ──► Qdrant kb_chunks
                                          │     └── open_record ──► Postgres  kb_records
                                          ├── history ───────────► Postgres  agent_sessions, agent_messages
                                          └── message log ───────► Postgres  messages table (fail-open)

app startup:        ping Postgres + Qdrant (a failure is logged, never fatal)
container startup:  alembic upgrade head, then uvicorn
one-off ingest:     python -m app.kb.ingest ──► corpus/KB-*.md ──► chunks ──► OpenAI embeddings
                                                 ──► Qdrant kb_chunks + Postgres kb_records
```

The API only reads the `kb_chunks` collection, through `search_kb`. The `app.kb` ingest command writes it.

## Repository Layout

- `backend/app/`: the FastAPI application
  - `api/`: HTTP routes (`health.py`, `auth.py`, `conversations.py`, `chat.py`, `records.py`, `tools.py`), route dependencies (`deps.py`), the JSON error body (`errors.py`) and the web chat mount (`spa.py`)
  - `agent/`: Zoomer's runtime (`runtime.py`), the turn events and their mapping from the SDK's stream (`streaming.py`), system prompt, per-turn context, the citation check (`citations.py`) and the tools (`tools/`: the envelope and its guard, `search_kb`, `open_record`)
  - `core/`: settings, logging setup, phone and name validation (`validators.py`)
  - `db/`: SQLAlchemy engine, models, fail-open write guard, message log
  - `kb/`: the knowledge base: record parsing (`corpus.py`), chunking (`chunking.py`), embeddings, Qdrant storage (`store.py`), the `kb_records` table (`records.py`), search and record lookups for the tools and the API (`knowledge_base.py`), and the command-line tools `ingest`, `search`, `check_corpus` and `eval_rephrase`
  - `middleware/`: per-request logging context
  - `services/`: OpenAI and Qdrant client constructors, users and the session cookie (`auth.py`), conversations (`conversations.py`), rate limits (`rate_limit.py`), turns and tool steps (`turns.py`)
- `backend/alembic/`: database migrations (`versions/0001_messages.py`, ...)
- `backend/corpus/`: the knowledge base, one Markdown record per file (`KB-001.md` …)
- `backend/eval/`: `rephrase.yaml`, rephrased questions for the retrieval check
- `backend/tests/`: pytest unit tests and test fakes
- `backend/scripts/entrypoint.sh`: container entrypoint
- `backend/pyproject.toml`, `backend/uv.lock`: the uv project (Python 3.12)
- `frontend/`: the web chat (Vite + React + TypeScript + Mantine)
  - `src/App.tsx`: picks the page: a loader, the sign-in chat or the chat page
  - `src/api/`: the fetch wrapper (`client.ts`), the server-sent event reader (`sse.ts`) and one module per API area (`auth.ts`, `conversations.ts`, `chat.ts`, `records.ts`, `tools.ts`)
  - `src/components/`: `ChatPage` (navbar + chat), `SignInFlow`, `ConversationList`, `ChatPanel` (message list + composer), `Header`, `MessageList`, `MessageBubble`, `MarkdownText`, `CitationChip`, `StepLog`, `RecordDrawer`, `ToolsModal`, `Composer`
  - `src/hooks/`: `useSession` (the signed-in user) and `useChat` (conversations, the open chat and the streaming reply)
  - `src/theme.ts`: the Mantine theme
  - `public/logo.svg`: the logo, also used as the favicon
- `.github/workflows/ci.yml`: the CI workflow
- `docs/retrieval.md`: chunking, the HNSW index and the rephrase check results
- `docs/architecture.md`: a chat turn: streaming, Stop and the one-running-turn lock, tools, the error envelope, the step cap, citations and what is stored
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
  - `GET /api/conversations/{id}/messages` → `[{id, role, content, turn_id, status, citations, steps}]`, oldest first; `status`, `citations` and `steps` are set on Zoomer's replies
  - `POST /api/chat/stream` `{conversation_id, message}` → server-sent events: `token {text}`, `tool_call {tool, args}`, `tool_result` (a step), then `citation {valid, invalid, missing}` and `done {turn_id, reply, status}`; `error {code, message}` when the turn breaks. Closing the connection stops the turn. 409 `REPLY_IN_PROGRESS` while another reply in the conversation is running; 422 on invalid input
  - `POST /api/chat` `{conversation_id, message}` → `{turn_id, reply, status, citations: {valid, invalid, missing}, steps: [{step, tool, args, success, code, record_ids, duration_ms}]}`, the same turn in one piece; same errors as the stream
  - `GET /api/records/{id}` → `{id, title, type, updated, header, body}`; 404 `NOT_FOUND`
  - `GET /api/tools/schema` → `[{name, description, parameters, strict}]`, read from the tool objects the agent gets
  - Every `/api/*` route except `/api/auth/*` needs a signed-in user (401 otherwise). Someone else's conversation is a 404. Over a rate limit is a 429 with `Retry-After`. These errors have the body `{"error": {"code", "message"}}`; the `message` is written for the customer.
  - `GET /openapi.json` is served in every mode, so API types can be generated from it
  - `/docs` and `/redoc` only when `DEBUG=true`
- Web chat: `GET /` and the files next to it (`/assets/*`, `/logo.svg`), when the image has a frontend build. Any other path gets FastAPI's JSON 404.
- Command-line tools, run from `backend/` or in the image's `/app`:
  - `python -m app.kb.ingest [--force] [--dry-run]`: load the corpus into Qdrant and `kb_records`
  - `python -m app.kb.search "query" [-k 5] [--type product] [--max-price 3000]`: search the knowledge base
  - `python -m app.kb.check_corpus [corpus_dir]`: consistency checks, no services or settings needed
  - `python -m app.kb.eval_rephrase [--file eval/rephrase.yaml] [-k 5]`: hit@1 and hit@k for rephrased questions

## Current Stack

- Runtime: Python 3.12, managed with uv. The Docker image installs from `uv.lock` with `uv sync --frozen`.
- Web: FastAPI + uvicorn, pydantic v2, pydantic-settings.
- LLM: OpenAI Agents SDK (`openai-agents`) on the OpenAI Responses API. Chat model `gpt-6-luna`, which rejects `temperature`, so the agent uses low reasoning effort instead.
- Persistence: Postgres 17 through async SQLAlchemy 2 + asyncpg. Alembic migrations are hand-written. Agent conversation history lives in Postgres too, through the Agents SDK's `SQLAlchemySession`.
- Vector store: Qdrant (server and `qdrant-client`, both v1.19). Embeddings: `text-embedding-3-small`, 1536 dimensions. Chunk sizes are counted with `tiktoken` (`cl100k_base`). Record headers are YAML, read with PyYAML.
- Logging: structlog on top of stdlib `logging`. JSON lines by default, colored console output when `DEBUG=true`.
- Frontend: npm (CI and the Docker image use Node.js 22), Vite 8, React 19, TypeScript 6.0, Mantine 9, `react-markdown` with `remark-gfm`, Tabler icons.
- Lint/format: ruff for the backend (line length 100, rules `E`, `F`, `I`, `UP`); oxlint and Prettier for the frontend (no semicolons, single quotes).
- Runtime environment: Docker Compose with `api`, `postgres` and `qdrant`.

## Architecture Notes

A chat turn goes through these steps:

1. `POST /api/chat/stream` (`app/api/chat.py`) validates `{conversation_id, message}`. `message` is stripped and 1–4000 characters. `POST /api/chat` takes the same body and runs the same turn.
2. Dependencies run first, so their errors are JSON responses before any event is sent: `get_current_user` reads the user from the session cookie (401), and `limit_chat` counts the message against the user's rate limit (429). `start_turn` then loads the conversation only if it belongs to the user (404) and starts a `running` turn with `TurnStore.start()`. A partial unique index (migration `0005`) allows one running turn per conversation, so a second message while Zoomer is still answering gets a 409. `start()` first marks running turns older than two minutes as `failed`, so a server that died mid-turn can't block a conversation. Then the conversation is titled after its first message and moved to the top of the list, and `TurnStore.retrieved_ids()` reads the records the tools returned in its earlier turns.
3. The route gets the `TurnRunner` (`app/agent/runtime.py`) through the `get_turn_runner` dependency (`app/api/deps.py`). `TurnRunner.stream()` builds a `TurnContext` with the `KnowledgeBase` and calls `Runner.run_streamed` with the runner's `Agent`, whose tools are `search_kb` and `open_record` (`app/agent/tools/`). `agent_events()` (`app/agent/streaming.py`) turns the SDK's stream into `Token`, `ToolCall` and `Step` events; a tool's result is the `Step` its guard recorded. The stream route sends them as SSE frames through FastAPI's `EventSourceResponse`, which also sends a `: ping` comment every 15 seconds of silence. `/api/chat` reads the stream to its end and returns the last event.
4. The agent's instructions are the static `AGENT_INSTRUCTIONS` (`app/agent/prompts.py`) plus the current date and time in UTC and the customer's name, recomputed on every run.
5. History comes from the SDK's `SQLAlchemySession` on the app's engine, with the conversation id as the session id. Its tables `agent_sessions` and `agent_messages` are created by migration `0004`, not by the SDK. The model sees only the last `HISTORY_WINDOW_TURNS` user turns (`window_history()`, the run's `session_input_callback`); stored rows are never deleted. The window cuts only on turn boundaries, so a tool call is never separated from its output.
6. Every request carries `prompt_cache_key = conversation:<conversation_id>`, and the run is capped at `AGENT_MAX_TURNS` (5) model calls. A run that needs more ends with `MAX_STEPS_TEXT` through the SDK's `max_turns` error handler, and the turn status is `max_steps`.
7. Any runtime error, or an empty answer, becomes `FALLBACK_TEXT`, and the turn status is `failed`. The turn still ends normally with a reply. These fixed texts are never streamed as tokens, so the final `done` event carries the stored reply and the web chat shows it in place of the streamed text.
8. For an `ok` turn, `check_citations()` (`app/agent/citations.py`) sorts the reply's `[KB-042]` citations into valid ones (a tool returned the record in this conversation) and invalid ones, and sets `missing` when this turn retrieved records but the reply cites none of them. Other turns get empty citations, because their texts cite nothing or are unfinished. When `MESSAGE_LOG_ENABLED=true`, `record_turn_messages()` writes the user row and the assistant row to the `messages` table through `pg_guard`. `TurnStore.finish()` stores the status, the citations and the tool steps, and the stream ends with `citation` and `done`.
9. When the client closes the connection (the Stop button, logging out or a closed tab), FastAPI cancels the stream. `TurnRunner.stream()` cancels the SDK run and stores the turn as `cancelled` with its tool steps. The reply written so far goes to the message log and into the agent history as an assistant message, so Zoomer knows what it already said; a turn stopped before any text has no reply row. Those writes run in a cancelled task, so they sit in a shielded `anyio` scope limited to `WRITE_TIMEOUT_S`. Any other exception after the stream started ends it with an `error` event.

**Tools.** Each tool is a `function_tool` wrapped in `tool_guard` (`app/agent/tools/envelope.py`). The tool returns a `ToolResult` (data and record ids) or raises `ToolError(code, message)`; the guard turns either one into the JSON envelope `{success: true, data}` or `{success: false, code, message}`, so a tool never raises. Any other exception becomes `UPSTREAM_ERROR` with a fixed message, and the exception text goes only to the log. The guard also appends a `Step` (tool, args, success, code, record ids, duration) to `TurnContext.steps`. Tools reach the knowledge base through `TurnContext.kb`, the `KnowledgeBase` (`app/kb/knowledge_base.py`) built in the lifespan; `GET /api/records/{id}` uses the same object. The SDK builds strict schemas from the signatures and docstrings: every property is required (optional ones are nullable) and `additionalProperties` is false. Details: `docs/architecture.md`.

**Message log writes are fail-open.** `pg_guard` (`app/db/guard.py`) bounds the write to 5 seconds, and logs and swallows any error. A database problem must never break a chat turn. The web chat reads transcripts from this table, so with `MESSAGE_LOG_ENABLED=false` reopened conversations look empty.

**Sign-in.** A scripted flow in code, never the model: `/api/auth/phone` signs in a known number or answers `need_name`, then `/api/auth/create` creates the account. There is no SMS code; the shop is fictional. `validate_phone` (`phonenumbers`, `PHONE_DEFAULT_REGION` for numbers without a country code) stores numbers as E.164, and `validate_name` allows 2–40 letters, spaces, hyphens and apostrophes, because the name goes into the instructions. `UserStore.get_or_create` is one upsert, so a phone always maps to one account. Starlette's `SessionMiddleware` keeps only `user_id` in the `zoomerfume_session` cookie, signed with `SESSION_SECRET` (HttpOnly, SameSite=Lax, 30 days). The cookie holds all session state, so any API replica can serve any request.

**Rate limits.** `RateLimiter.hit()` (`app/services/rate_limit.py`) counts requests per key in fixed one-minute windows in the `rate_limits` table, with one atomic `INSERT … ON CONFLICT DO UPDATE … RETURNING count`. Keys are `chat:user:<id>` (`RATE_LIMIT_CHAT_PER_MIN`, checked in `limit_chat`) and `auth:ip:<client address>` (`RATE_LIMIT_AUTH_PER_MIN`, on `/api/auth/phone` and `/api/auth/create`). When a key opens a new window, rows older than a day are deleted. Postgres holds the counters, so the limits stay correct with several replicas.

**Data access.** Routes reach Postgres through small stores (`UserStore`, `ConversationStore`, `RateLimiter`, `TurnStore`), each built per request on the `get_db` session. Tests replace the stores, not the database.

**Startup and shutdown.** `create_app(settings=None)` (`app/main.py`) loads the settings (or takes the ones passed in), sets up logging and stores the settings on `app.state`. Nothing runs at import time. After the routers it calls `mount_web_chat()` (`app/api/spa.py`), which mounts the frontend build at `/` only if `backend/static/index.html` exists (`/app/static` in the image). Without a build, as in unit tests or a backend run on the host, the app serves the API only. The lifespan creates the OpenAI and Qdrant clients and the SQLAlchemy engine, points the Agents SDK at the app's own `AsyncOpenAI` client through `set_default_openai_client`, and stores the session factory (`sessionmaker`), the `KnowledgeBase` and one `TurnRunner` on `app.state`. It then pings Postgres and Qdrant; if either is down, it logs the error and keeps starting, and sign-in and chat fail until Postgres is back. Shutdown closes the clients and disposes the engine. `GET /health` is a liveness check that always returns `{"status": "ok"}`.

**Dependencies.** Code gets settings and clients passed in; no module reads settings at import time. Routes get lifespan objects through FastAPI dependencies in `app/api/deps.py`, which read `app.state`. Add a new dependency there when a route first needs a new shared object.

**Knowledge base.** Records are `KB-NNN.md` files with a YAML header (`id`, `title`, `type`, `updated`; products also have brand, concentration, family, gender, seasons, sizes with prices and points, an optional decant and availability) and a Markdown body in `##` sections. `RecordHeader` (`app/kb/corpus.py`) validates the header, and the file name must match the id. Records link to each other as plain IDs ("see KB-052"), never in square brackets, which is Zoomer's citation format. `chunk_record()` splits a body at `##` headings, packs neighbouring sections up to 500 tokens, splits an oversized section on paragraphs and then sentences, starts every chunk after the first with the last ~75 tokens of the previous one, and gives each chunk a `Title › Sections` breadcrumb that is embedded with it. Ingest skips records whose file hash matches `kb_records.content_hash`, embeds the rest in batches, upserts points with id `uuid5(record id, chunk index)` and deletes leftover chunks, then deletes records that left the corpus. A newly created collection makes it a full run. The collection uses cosine distance, HNSW `m=16`, `ef_construct=100` and `indexing_threshold=10` kB, because Qdrant's default threshold (10,000 kB) is bigger than the whole corpus and would leave it unindexed; ingest waits for the index and prints `indexed_vectors_count`. The payload has `source`, `title`, `chunk_index`, `record_id`, `type`, `updated`, `section`, `text` and, for products, `price` (the cheapest bottle), with payload indexes on `record_id`, `type` and `price`. `search()` (`app/kb/search.py`) embeds the query and filters by `type` and `max_price`. Postgres commits the new hashes only after Qdrant has the points, so a failed run is simply repeated.

**Migrations.** The container entrypoint runs `alembic upgrade head` before it starts uvicorn. `alembic/env.py` reads the DSN from the app settings, so the database URL is defined in exactly one place.

**Web chat.** A single page with no router and no state library. On load, `useSession` calls `/api/me`; a 401 shows `SignInFlow`, where Zoomer asks for the phone and then the name as chat bubbles. Zoomer's first question is in the frontend, and every later line comes from the API's `message`. When signed in, `ChatPage` remounts per user. `useChat` loads the conversation list, opens the most recent conversation with its transcript, and keeps the rest in React state. "New chat" only clears the view: the first message creates the conversation, so the list never fills with empty chats. Replies stream in: `useChat` reads `/api/chat/stream` through `src/api/sse.ts`, which buffers network chunks into events and skips the keep-alive pings. The reply bubble shows a loader and the tool Zoomer is using until the first token arrives, and `done` replaces the streamed text with the stored reply. While a reply streams, the composer's Send button turns into Stop, which aborts the request; the partial reply stays with a "Stopped" note, as it does after a reload. `useChat` also aborts the request when it unmounts (on log out, for example), so the turn stops instead of running on in the background. Sending and switching chats are blocked while a reply streams or a transcript loads. API errors with a code show their `message` (a rate limit, or a 409 from a second tab, for example); other failures show a generic line. All requests go through `src/api/client.ts`. The composer keeps its own draft and `MessageBubble` is memoized, so typing and streamed tokens re-render only the parts that changed. Assistant replies render as Markdown through `MarkdownText` (GFM tables included, raw HTML is not rendered); user messages render as plain text. In a reply, each `[KB-042]` citation becomes a `CitationChip` (red when invalid), with a "Sources" row of the valid ones under the bubble; a chip opens `RecordDrawer` with the full record from `/api/records/{id}`. `StepLog` under each reply lists the tool calls (collapsed) or says "No tools used", and flags invalid or missing citations. The header's Tools button opens `ToolsModal` with the tool schemas. On phones, Tools and Log out are icon buttons, so the header fits. The color scheme follows the system, and the header toggle overrides it. Keep the UI minimal and functional: stock Mantine components and the theme in `theme.ts`. In development the Vite dev server proxies `/api` to `localhost:8000`, so the browser never needs CORS. In the image, the first Docker stage builds the frontend and the runtime stage copies `frontend/dist` to `/app/static`.

## Tests

Unit tests live in `backend/tests/` and run with pytest (`asyncio_mode = "auto"`). They never call OpenAI, Postgres or Qdrant:

- `conftest.py` builds `Settings` in code with `_env_file=None`, so a real key in `.env` is never read.
- The `client` fixture overrides `get_turn_runner`, `get_user_store`, `get_conversation_store`, `get_rate_limiter`, `get_turn_store` and `get_knowledge_base` with in-memory fakes from `tests/fakes.py`, and uses `TestClient` without `with`, so the lifespan never runs and nothing touches Postgres. The client keeps cookies, so the `user` fixture signs in through `/api/auth/phone` like a browser.
- The fakes don't run SQL. The upserts in `UserStore` and `RateLimiter` and the queries in `TurnStore` (including the one-running-turn lock) are checked against a real database in the smoke checks.
- Runtime tests stream the real agent loop on the SDK's `ScriptedModel` (`agents.testing`), with in-memory history, a fake knowledge base and a fake turn store; the Stop test closes the stream while a tool is still running. Tool tests call each tool through `on_invoke_tool`, the way the agent loop does.
- Chat API tests run both endpoints on a `FakeTurnRunner` that streams canned events, and read the stream route's server-sent events from the response body.
- Web chat tests mount a tiny fake build from a temporary directory.
- Knowledge base tests cover header parsing, the corpus checks (including a run over the shipped `backend/corpus/`), chunk limits, overlap and breadcrumbs, point ids and search filters. `tiktoken` downloads the `cl100k_base` encoding on first use and caches it, so the first chunking test needs network access.

Keep tests few and focused: the happy path plus the errors that matter. Replace external services with fakes at the boundary instead of starting them. The frontend has no test suite; it is checked by lint, formatting and the type-checked build.

CI (`.github/workflows/ci.yml`) runs on pull requests and pushes to `dev` and `main`. Job `backend` runs `uv sync --frozen`, `ruff check`, `ruff format --check` and `pytest` in `backend/`. Job `frontend` runs `npm ci`, `npm run lint`, `npm run format:check` and `npm run build` in `frontend/`. Job `docker` builds the image with Buildx and caches its layers in the GitHub Actions cache. It pulls Docker Hub base images through the `mirror.gcr.io` mirror, because Docker Hub rate-limits anonymous pulls from shared runner IPs (429); BuildKit falls back to Docker Hub if the mirror fails.

## Configuration

The app reads environment variables only, through `app/core/config.py`. For local runs, pydantic-settings also reads `../.env` and `./.env`, so one `.env` at the repo root works both for Compose and for a run from `backend/`. Real environment variables take precedence over `.env` values.

- `.env.example` is the committed template. `.env` holds real secrets and is git-ignored.
- `SESSION_SECRET` is required and must be at least 32 characters (`openssl rand -hex 32`). Changing it signs everyone out.
- Compose passes the root `.env` into the `api` container (`env_file`). Postgres credentials also have defaults in `docker-compose.yml`.
- Inside Compose, services reach each other by service name (`postgres`, `qdrant`). A backend run on the host must point `DATABASE_URL` and `QDRANT_URL` at `localhost` (see Common Commands).
- The knowledge base settings are `QDRANT_COLLECTION` (`kb_chunks`), `CORPUS_DIR` (`corpus`, relative to the working directory: `backend/` on the host, `/app` in the image), `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS`. Changing the model or dimensions needs a new collection.
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
curl -N -b jar -X POST localhost:8000/api/chat/stream \
  -H 'content-type: application/json' -d '{"conversation_id": "<uuid>", "message": "vanilla and tobacco under 3000 UAH?"}'
# while that one streams, a second message to the same conversation gets a 409;
# curl --max-time 3 on a long question stops it halfway (turn status cancelled)
curl -b jar localhost:8000/api/records/KB-026      # a cited record
curl -b jar localhost:8000/api/tools/schema        # the tool schemas
docker compose exec postgres psql -U zoomer -d zoomerfume \
  -c 'select role, left(content, 60), created_at from messages order by id desc limit 4'
docker compose exec postgres psql -U zoomer -d zoomerfume \
  -c 'select t.status, t.citations, s.tool, s.record_ids from turns t left join tool_steps s on s.turn_id = t.id order by t.started_at desc limit 5'
```

Knowledge base (needs the stack up; ingest and search call the OpenAI embeddings API, a full ingest costs well under a cent):

```bash
docker compose run --rm api python -m app.kb.ingest            # second run: everything skipped
docker compose run --rm api python -m app.kb.search "vanilla and tobacco" --type product --max-price 3000
docker compose run --rm api python -m app.kb.eval_rephrase     # target: hit@5 ≥ 90%
curl -s localhost:6333/collections/kb_chunks                   # points_count, indexed_vectors_count
docker compose exec postgres psql -U zoomer -d zoomerfume -c 'select id, type, title from kb_records limit 5'
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
uv run python -m app.kb.check_corpus
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
- Agent history and transcripts both live in Postgres, so they survive a rebuilt or recreated `api` container. Only `docker compose down -v` (it deletes the `postgres_data` volume) makes Zoomer forget.
- Localhost cookies are shared between ports, so the Vite dev server (`:5173`) and the API (`:8000`) share the `zoomerfume_session` cookie. The cookie has its own name so it doesn't clash with other local apps.
- Two HTTP client libraries are installed: `openai` 3.x (and so the Agents SDK) uses `httpx2`/`httpcore2`, while `qdrant-client` uses `httpx` 0.28. Their loggers are quieted separately in `app/core/logging.py`. OpenAI failures surface as `openai.*` exceptions, not `httpx` ones.
- TypeScript stays on 6.0, the version the Vite template pins.
- The production build warns that the JS bundle is over 500 kB (Mantine, Markdown and icons). It is a single local page, so there is no code splitting yet.
- Every chat check calls OpenAI and costs a little. Keep manual checks short.
- After changing the chunking or the embedding model, run ingest with `--force`: the file hashes haven't changed, so a normal run would skip every record.
- `indexed_vectors_count` equals `points_count` only on a fresh collection. After any re-embed or delete it stays higher, because Qdrant vacuums only segments with at least 1,000 vectors. Search is not affected.
- `.dockerignore` excludes only the repo docs (`README.md`, `CLAUDE.md`, `docs/`). The corpus is Markdown, so a broader `*.md` rule would ship an image with no records.

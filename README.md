# Zoomerfume

**Zoomer** is the AI shop assistant of **Zoomerfume**, a fictional Ukrainian online perfume shop. It recommends perfumes by taste, budget, occasion and season, compares products, answers shop questions (delivery, returns, payment, loyalty) and gives general perfume advice. The goal is a *grounded* assistant: answers about the shop come from a knowledge base the model searches through tools, with citations to the records it used, not from the model's memory.

> **Status: early version.** The current version is a web chat with Zoomer on top of a streaming chat API. Customers sign in with a phone number and keep several conversations each. Zoomer looks things up in the shop's knowledge base (96 records: products, policies, FAQ, company pages, news) through two tools, `search_kb` and `open_record`, and cites the records it used. A third tool, `save_note`, keeps notes for the customer, such as a wishlist, and can only ever write for the signed-in customer. Replies stream in token by token and can be stopped. Citations show up as chips that open the full record, every answer has a step log of the tools it called and shows what it cost, and the notes panel shows the saved notes. The static system prompt is cached, and `/cost` prints what a conversation cost per turn.

## Stack

- **Backend:** Python 3.12, FastAPI, [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), pydantic-settings, structlog, uv
- **Models:** `gpt-6-luna` for chat (configurable); `text-embedding-3-small` for the knowledge base
- **Data:** Postgres (async SQLAlchemy + Alembic), Qdrant (vector search)
- **Runtime:** Docker Compose; Kubernetes (kind) planned
- **Frontend:** React + TypeScript + Vite + Mantine, served by the same FastAPI app

## Architecture

```
Browser (web chat)
   │  / and /api/*
   ▼
api (FastAPI + Agents SDK) ─────► OpenAI (chat + embeddings)
   │        │
   │        └───────────────────► Qdrant (knowledge-base vectors)
   ▼
Postgres (users, conversations, agent history, turns and tool steps, message log, rate limits,
          knowledge base records, notes, model call costs)
```

One Docker image runs the API and serves the built web chat. Postgres and Qdrant run as separate services. How a chat turn works (streaming, Stop, tools, notes, the error envelope, the 5-step cap, citations, prompt caching and costs): [docs/architecture.md](docs/architecture.md).

## Quick start (Docker)

Requirements: Docker Desktop and an OpenAI API key.

```bash
cp .env.example .env          # then set OPENAI_API_KEY and SESSION_SECRET in .env
docker compose up --build
```

`SESSION_SECRET` signs the session cookie; generate one with `openssl rand -hex 32`.

Open http://localhost:8000. Zoomer asks for your phone number, and for your name if the number is new. There is no SMS code, since the shop is fictional. Your conversations are listed on the left; "New chat" starts another one. Log out to switch to a different customer.

To answer shop questions, Zoomer needs the knowledge base loaded first (see [Load the knowledge base](#load-the-knowledge-base)). Then ask something like "vanilla and tobacco under 3,000 ₴?": while Zoomer searches you see which tool it is using, then the answer streams in. It cites records as chips (click one to read the full record), and the line under it shows which tools Zoomer used. A general question such as "EDP vs EDT?" shows "No tools used". Ask Zoomer to add a perfume to your wishlist and the note shows up in the **Notes** panel on the right (behind the **Notes** button on smaller screens). The Stop button next to the message box stops a reply halfway; what Zoomer wrote so far stays. Under each answer you see what it cost, and typing `/cost` shows the whole conversation's cost per turn (see [Caching and cost](#caching-and-cost)). The **Tools** button shows the exact tool schemas the model receives.

`docker compose up` also loads `docker-compose.override.yml` (auto-reload, host ports for Postgres and Qdrant). Add `--watch` to sync backend code changes into the running container.

Or talk to the API directly. The session lives in a cookie, so keep a cookie jar:

```bash
curl -c jar -b jar -X POST localhost:8000/api/auth/phone \
  -H 'content-type: application/json' -d '{"phone": "050 111 22 33"}'
# → {"status": "need_name", ...} for a new number
curl -c jar -b jar -X POST localhost:8000/api/auth/create \
  -H 'content-type: application/json' -d '{"phone": "050 111 22 33", "name": "Mary"}'
curl -N -b jar -X POST localhost:8000/api/chat/stream \
  -H 'content-type: application/json' -d '{"message": "vanilla and tobacco under 3000 UAH?"}'
# → server-sent events: start {"conversation_id": "<conversation id>", "turn_id": "..."},
#   tool_call, tool_result, token, token, …, citation, usage, done
curl -b jar -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"conversation_id": "<conversation id>", "message": "add the first one to my wishlist"}'
# → {"conversation_id": "...", "turn_id": "...", "reply": "Added ... [KB-026]", "status": "ok",
#    "citations": {"valid": ["KB-026"], "invalid": [], "missing": false},
#    "steps": [{"step": 1, "tool": "save_note", "args": {"text": "..."}, "success": true, ...}],
#    "usage": {"calls": 2, "input_tokens": 14967, "cached_tokens": 14725, ..., "cost_usd": "0.000200950"}}
curl -b jar -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' -d '{"conversation_id": "<conversation id>", "message": "/cost"}'
# → {"turn_id": null, "reply": "**What this chat cost** ...| # | Time | Calls | ...", "status": "ok"}
curl -b jar localhost:8000/api/records/KB-026      # the cited record in full
curl -b jar localhost:8000/api/notes               # the customer's notes, newest first
```

A message without a `conversation_id` starts a new conversation, titled after the message; the stream's first event, `start`, carries its id. Send another message with that `conversation_id` to continue the conversation. `/api/chat/stream` sends the reply as it is written; `/api/chat` runs the same turn and returns it in one piece. A conversation answers one message at a time: a message sent while a reply is still running gets a 409. Health check: `curl localhost:8000/health`.

## Why the model can never pass a user id

`save_note` is the only tool that writes, and its schema has a single property, `text`. The **Tools** button (or `GET /api/tools/schema`) shows it exactly as the model receives it: strict mode, `additionalProperties: false`, no user id anywhere.

The customer comes from the signed session cookie, never from the model. For every message, `build_tools(user_id)` (`backend/app/agent/tools/__init__.py`) builds `save_note` with the signed-in customer's id captured in a closure. The run context the tools share holds no user id, so the closure is the only way the tool knows whose note it writes. The schema doesn't change with the user, so every customer's model calls see identical tool definitions.

What if someone tried to pass one anyway? The model can't: in strict mode the API only lets it produce arguments that match the schema, and the schema has no `user_id`. A hand-made tool call with an extra `user_id` doesn't get far either: the Agents SDK validates the arguments against the function's signature and drops the unknown key, and the note still goes to the signed-in customer. A unit test calls the tool that way and checks where the note lands.

Zoomer saves a note only when the customer asks for one; that rule lives in the prompt.

## Caching and cost

Every answer shows what it cost, e.g. "$0.00047 · 2 calls · 62% cached". Type `/cost` in a chat to see the whole conversation: one row per turn with the model calls, input, cached, cache-write and output tokens and the cost, then the total and the share of input tokens read from the cache. The backend answers `/cost` from the `llm_calls` table without calling the model, so it costs nothing and never enters Zoomer's history; it stays in the transcript.

How the prompt gets cached:

- The system prompt (`backend/app/agent/prompts.py`, about 7.9 KB or 1,800 tokens) is static: the same text for every customer and every call. With the tool schemas it is well over OpenAI's 1,024-token caching minimum.
- It opens every request as a developer message with an explicit cache breakpoint (`prompt_cache_breakpoint`). The API doesn't allow a breakpoint on the top-level `instructions`, so the run's `call_model_input_filter` moves the instructions into the input.
- Everything volatile comes last. The current Kyiv time and the customer's name are a developer note at the very end of each call's input, and the note is never stored. Search results are tool outputs in the history. So each request repeats the previous one up to its newest messages, and OpenAI's implicit breakpoint at the end of the newest user message or tool output lets the next call read all of it from the cache.
- Every request carries `prompt_cache_key = conversation:<id>`, so each conversation has its own cache.

**Why turn 1 starts with a cache write:** a new conversation has a new cache key, so nothing is cached for it yet. Its first call has nothing to read and writes the prompt and the message to the cache, billed at 1.25× the input price. Every later call, including a second call in turn 1 after a tool, reads what came before at a tenth of the input price and writes only what is new. A live conversation:

| Turn | Message | Calls | Input | Cached | Cache write | Cost |
|---:|---|---:|---:|---:|---:|---:|
| 1 | "hi! what is the difference between EDT and EDP?" | 1 | 2,213 | 0 | 2,182 | $0.000304 |
| 2 | "something warm with vanilla for winter under 3000 UAH?" (`search_kb`) | 2 | 7,158 | 4,439 | 2,657 | $0.000501 |
| 3 | "if I order the first one right now, can it arrive in Kyiv today?" (`search_kb`) | 2 | 12,436 | 9,898 | 2,476 | $0.000476 |
| 4 | "add the first one to my wishlist please" (`save_note`) | 2 | 14,967 | 14,725 | 180 | $0.000201 |

The cached prefix starts over when the history window slides (after `HISTORY_WINDOW_TURNS` turns the oldest turn leaves the input; the explicit breakpoint means the static prompt can still be read), when the prompt or the tools change, and after 30 minutes without a request.

Costs come from `backend/app/services/pricing.py`, in USD per million tokens: `gpt-6-luna` input 0.10, cached input 0.01, cache write 0.125, output 0.50; `text-embedding-3-small` 0.02. The API's `input_tokens` already include the cached and cache-write tokens, so a call costs uncached × input + cached × cached input + written × cache write + output × output, computed with `Decimal`. A hook on the agent run records every chat model call of a turn, the searches record their embedding calls, and all of them are stored in `llm_calls` when the turn ends. An ingest run stores one row for its embeddings.

## Load the knowledge base

The knowledge base lives in `backend/corpus/`: one Markdown file per record. Zoomer searches it to answer shop questions. Load it into Qdrant (and the `kb_records` table) once the stack is up:

```bash
docker compose run --rm api python -m app.kb.ingest
# Records: 96 total, 96 changed, 0 skipped, 0 deleted
# Chunks: 206 embedded, 77,554 tokens
# Qdrant kb_chunks: 206 points, 206 indexed vectors (HNSW)
```

Run it again after editing the corpus. Unchanged records are skipped, so a re-run only embeds what changed; `--force` re-embeds everything and `--dry-run` shows what would change. A full load costs well under one cent.

Search it and check retrieval quality:

```bash
docker compose run --rm api python -m app.kb.search "something warm for winter" --type product --max-price 3000
docker compose run --rm api python -m app.kb.eval_rephrase    # hit@1 / hit@5 on rephrased questions
```

How chunking, the HNSW index and the rephrase check work, with results: [docs/retrieval.md](docs/retrieval.md).

## Local development (without Docker for the API)

Requirements: [uv](https://docs.astral.sh/uv/). It installs Python 3.12 itself.

```bash
docker compose up -d postgres qdrant     # the data services still run in Docker

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn --factory app.main:create_app --reload
```

When the API runs on the host, point it at `localhost` instead of the Compose service names, e.g. by exporting these (environment variables take precedence over `.env`):

```bash
export DATABASE_URL=postgresql+asyncpg://zoomer:zoomer@localhost:5432/zoomerfume
export QDRANT_URL=http://localhost:6333
```

Lint, format and tests:

```bash
uv run ruff check .
uv run ruff format .
uv run pytest        # unit tests; no running services or API key needed
uv run python -m app.kb.check_corpus   # corpus consistency checks
```

The web chat runs on the Vite dev server with hot reload. It needs Node.js (CI and the Docker image use 22) and the API on port 8000, from Compose or uvicorn:

```bash
cd frontend
npm ci
npm run dev          # http://localhost:5173, proxies /api to localhost:8000
npm run lint         # oxlint
npm run format       # Prettier
npm run build        # type-check and build into dist/
```

The web chat's API types are generated from the backend's OpenAPI schema, so they can't drift from the API. After changing a route or one of its models, regenerate both files:

```bash
cd backend && uv run python -m app.api.openapi      # writes backend/openapi.json, no services needed
cd ../frontend && npm run api:types                 # writes frontend/src/api/schema.d.ts
```

CI (GitHub Actions) runs the backend lint, format and test checks and the frontend lint, format and build checks on every pull request into `dev` and `main`, fails when either generated file is out of date, and builds the Docker image.

## Configuration

All settings come from environment variables (`.env` for local runs). See `.env.example` for the full list. The main ones:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | (required) | OpenAI access |
| `CHAT_MODEL` | `gpt-6-luna` | Model behind Zoomer |
| `AGENT_MAX_TURNS` | `5` | Max model calls per message; past it Zoomer says it couldn't finish |
| `HISTORY_WINDOW_TURNS` | `12` | How many recent user turns the model sees |
| `DATABASE_URL` | local Compose DSN | Postgres connection (asyncpg) |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant connection |
| `QDRANT_COLLECTION` | `kb_chunks` | Qdrant collection for the knowledge base |
| `CORPUS_DIR` | `corpus` | Folder with the knowledge base records |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model that embeds the knowledge base and search queries |
| `MESSAGE_LOG_ENABLED` | `true` | Write every exchange to the `messages` table; the web chat loads transcripts from it |
| `SESSION_SECRET` | (required) | Signs the session cookie, at least 32 characters |
| `PHONE_DEFAULT_REGION` | `UA` | Region for phone numbers typed without a country code |
| `RATE_LIMIT_CHAT_PER_MIN` | `20` | Chat messages per customer per minute |
| `RATE_LIMIT_AUTH_PER_MIN` | `10` | Sign-in attempts per IP address per minute |

## Project layout

```
zoomerfume/
├── backend/
│   ├── app/
│   │   ├── api/          HTTP routes (health, auth, conversations, chat, records, tool schemas, notes), web chat mount, OpenAPI export
│   │   ├── agent/        Zoomer: agent runtime, turn events, prompt and model input order, usage hook, per-turn context, tools, citation check
│   │   ├── core/         settings, logging, input validation
│   │   ├── db/           SQLAlchemy engine, models, message log
│   │   ├── kb/           knowledge base: parsing, chunking, ingest, search, checks
│   │   ├── middleware/   request logging context
│   │   └── services/     OpenAI and Qdrant clients, users, conversations, rate limits, turns, notes, prices, usage, the /cost report
│   ├── alembic/          database migrations
│   ├── corpus/           knowledge base records (KB-001.md …)
│   ├── eval/             rephrased questions for the retrieval check
│   ├── scripts/          container entrypoint
│   ├── tests/            pytest unit tests
│   ├── openapi.json      the API's OpenAPI schema (generated)
│   └── pyproject.toml    uv project (Python 3.12)
├── frontend/
│   ├── src/              React app: pages, components, hooks, API client and generated API types, theme
│   ├── public/           logo
│   └── package.json      npm project
├── docs/retrieval.md             chunking, HNSW and retrieval results
├── docs/architecture.md          a chat turn: streaming, Stop, tools, notes, error envelope, step cap, citations, caching and costs
├── .github/workflows/ci.yml      CI pipeline
├── Dockerfile
├── docker-compose.yml            api + postgres + qdrant
├── docker-compose.override.yml   dev overrides
└── .env.example
```

## Disclaimer

Zoomerfume is a **fictional shop** made for this project. Perfume names refer to real products, and brand names belong to their owners, but all shop data (prices, stock, policies, contacts) is invented. The project is not affiliated with any brand or retailer. Zoomer is an AI assistant and can make mistakes.

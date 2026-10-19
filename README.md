# Zoomerfume

**Zoomer** is the AI shop assistant of **Zoomerfume**, a fictional Ukrainian online perfume shop. It recommends perfumes by taste, budget, occasion and season, compares products, answers shop questions (delivery, returns, payment, loyalty) and gives general perfume advice. The goal is a *grounded* assistant: answers about the shop come from a knowledge base the model searches through tools, with citations to the records it used, not from the model's memory.

> **Status: early version.** The current version is a web chat with Zoomer on top of a non-streaming chat API. Customers sign in with a phone number and keep several conversations each. Zoomer looks things up in the shop's knowledge base (96 records: products, policies, FAQ, company pages, news) through two tools, `search_kb` and `open_record`, and cites the records it used. Citations show up as chips that open the full record, and every answer has a step log of the tools it called. Replies are not streamed yet.

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
          knowledge base records; later notes, costs)
```

One Docker image runs the API and serves the built web chat. Postgres and Qdrant run as separate services. How a chat turn works (tools, the error envelope, the 5-step cap, citations): [docs/architecture.md](docs/architecture.md).

## Quick start (Docker)

Requirements: Docker Desktop and an OpenAI API key.

```bash
cp .env.example .env          # then set OPENAI_API_KEY and SESSION_SECRET in .env
docker compose up --build
```

`SESSION_SECRET` signs the session cookie; generate one with `openssl rand -hex 32`.

Open http://localhost:8000. Zoomer asks for your phone number, and for your name if the number is new. There is no SMS code, since the shop is fictional. Your conversations are listed on the left; "New chat" starts another one. Log out to switch to a different customer.

To answer shop questions, Zoomer needs the knowledge base loaded first (see [Load the knowledge base](#load-the-knowledge-base)). Then ask something like "vanilla and tobacco under 3,000 ₴?": the answer cites records as chips (click one to read the full record), and the line under it shows which tools Zoomer used. A general question such as "EDP vs EDT?" shows "No tools used". The **Tools** button shows the exact tool schemas the model receives.

`docker compose up` also loads `docker-compose.override.yml` (auto-reload, host ports for Postgres and Qdrant). Add `--watch` to sync backend code changes into the running container.

Or talk to the API directly. The session lives in a cookie, so keep a cookie jar:

```bash
curl -c jar -b jar -X POST localhost:8000/api/auth/phone \
  -H 'content-type: application/json' -d '{"phone": "050 111 22 33"}'
# → {"status": "need_name", ...} for a new number
curl -c jar -b jar -X POST localhost:8000/api/auth/create \
  -H 'content-type: application/json' -d '{"phone": "050 111 22 33", "name": "Mary"}'
curl -b jar -X POST localhost:8000/api/conversations
# → {"id": "<conversation id>", "title": null}
curl -b jar -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"conversation_id": "<conversation id>", "message": "vanilla and tobacco under 3000 UAH?"}'
# → {"reply": "... [KB-026]", "turn_id": "...",
#    "citations": {"valid": ["KB-026"], "invalid": [], "missing": false},
#    "steps": [{"step": 1, "tool": "search_kb", "args": {...}, "success": true, "record_ids": [...], ...}]}
curl -b jar localhost:8000/api/records/KB-026      # the cited record in full
```

Send another message with the same `conversation_id` to continue the conversation. Health check: `curl localhost:8000/health`.

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

CI (GitHub Actions) runs the backend lint, format and test checks and the frontend lint, format and build checks on every pull request into `dev` and `main`, and builds the Docker image.

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
│   │   ├── api/          HTTP routes (health, auth, conversations, chat, records, tool schemas), web chat mount
│   │   ├── agent/        Zoomer: agent runtime, prompt, per-turn context, tools, citation check
│   │   ├── core/         settings, logging, input validation
│   │   ├── db/           SQLAlchemy engine, models, message log
│   │   ├── kb/           knowledge base: parsing, chunking, ingest, search, checks
│   │   ├── middleware/   request logging context
│   │   └── services/     OpenAI and Qdrant clients, users, conversations, rate limits, turns
│   ├── alembic/          database migrations
│   ├── corpus/           knowledge base records (KB-001.md …)
│   ├── eval/             rephrased questions for the retrieval check
│   ├── scripts/          container entrypoint
│   ├── tests/            pytest unit tests
│   └── pyproject.toml    uv project (Python 3.12)
├── frontend/
│   ├── src/              React app: pages, components, hooks, API client, theme
│   ├── public/           logo
│   └── package.json      npm project
├── docs/retrieval.md             chunking, HNSW and retrieval results
├── docs/architecture.md          a chat turn: tools, error envelope, step cap, citations
├── .github/workflows/ci.yml      CI pipeline
├── Dockerfile
├── docker-compose.yml            api + postgres + qdrant
├── docker-compose.override.yml   dev overrides
└── .env.example
```

## Disclaimer

Zoomerfume is a **fictional shop** made for this project. Perfume names refer to real products, and brand names belong to their owners, but all shop data (prices, stock, policies, contacts) is invented. The project is not affiliated with any brand or retailer. Zoomer is an AI assistant and can make mistakes.

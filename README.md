# Zoomerfume

**Zoomer** is the AI shop assistant of **Zoomerfume**, a fictional Ukrainian online perfume shop. It recommends perfumes by taste, budget, occasion and season, compares products, answers shop questions (delivery, returns, payment, loyalty) and gives general perfume advice. The goal is a *grounded* assistant: answers about the shop come from a knowledge base the model searches through tools, with citations to the records it used, not from the model's memory.

> **Status: early version.** The current version is a web chat with Zoomer on top of a non-streaming chat API, with no tools yet. Customers sign in with a phone number and keep several conversations each. Zoomer can talk about perfume in general, but it can't look up Zoomerfume's catalog, prices or policies, and it says so.

## Stack

- **Backend:** Python 3.12, FastAPI, [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), pydantic-settings, structlog, uv
- **Models:** `gpt-6-luna` for chat (configurable); `text-embedding-3-small` for the knowledge base (planned)
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
Postgres (users, conversations, message log, rate limits; later notes, costs)
```

One Docker image runs the API and serves the built web chat. Postgres and Qdrant run as separate services.

## Quick start (Docker)

Requirements: Docker Desktop and an OpenAI API key.

```bash
cp .env.example .env          # then set OPENAI_API_KEY and SESSION_SECRET in .env
docker compose up --build
```

`SESSION_SECRET` signs the session cookie; generate one with `openssl rand -hex 32`.

Open http://localhost:8000. Zoomer asks for your phone number, and for your name if the number is new. There is no SMS code, since the shop is fictional. Your conversations are listed on the left; "New chat" starts another one. Log out to switch to a different customer.

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
  -d '{"conversation_id": "<conversation id>", "message": "hi! what should I wear on a summer date?"}'
# → {"reply": "..."}
```

Send another message with the same `conversation_id` to continue the conversation. Health check: `curl localhost:8000/health`.

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
| `AGENT_MAX_TURNS` | `15` | Max agent-loop iterations per message |
| `HISTORY_WINDOW_TURNS` | `12` | How many recent user turns the model sees |
| `DATABASE_URL` | local Compose DSN | Postgres connection (asyncpg) |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant connection |
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
│   │   ├── api/          HTTP routes (health, auth, conversations, chat), web chat mount
│   │   ├── agent/        Zoomer: agent runtime, prompt, per-turn context
│   │   ├── core/         settings, logging, input validation
│   │   ├── db/           SQLAlchemy engine, models, message log
│   │   ├── middleware/   request logging context
│   │   └── services/     OpenAI and Qdrant clients, users, conversations, rate limits
│   ├── alembic/          database migrations
│   ├── scripts/          container entrypoint
│   ├── tests/            pytest unit tests
│   └── pyproject.toml    uv project (Python 3.12)
├── frontend/
│   ├── src/              React app: pages, components, hooks, API client, theme
│   ├── public/           logo
│   └── package.json      npm project
├── .github/workflows/ci.yml      CI pipeline
├── Dockerfile
├── docker-compose.yml            api + postgres + qdrant
├── docker-compose.override.yml   dev overrides
└── .env.example
```

## Disclaimer

Zoomerfume is a **fictional shop** made for this project. Perfume names refer to real products, but all shop data (prices, stock, policies, contacts) is invented. The project is not affiliated with any brand or retailer. Zoomer is an AI assistant and can make mistakes.

# Zoomerfume

**Zoomer** is the AI shop assistant of **Zoomerfume**, a fictional Ukrainian online perfume shop. It recommends perfumes by taste, budget, occasion and season, compares products, answers shop questions (delivery, returns, payment, loyalty) and gives general perfume advice. The goal is a *grounded* assistant: answers about the shop come from a knowledge base the model searches through tools, with citations to the records it used, not from the model's memory.

> **Status: early version.** The current version is a web chat with Zoomer on top of a non-streaming chat API, with no tools yet. Zoomer can talk about perfume in general, but it can't look up Zoomerfume's catalog, prices or policies, and it says so.

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
Postgres (message log; later users, conversations, notes, costs)
```

One Docker image runs the API and serves the built web chat. Postgres and Qdrant run as separate services.

## Quick start (Docker)

Requirements: Docker Desktop and an OpenAI API key.

```bash
cp .env.example .env          # then set OPENAI_API_KEY in .env
docker compose up --build
```

Open http://localhost:8000 and chat with Zoomer. "New chat" starts a fresh conversation.

`docker compose up` also loads `docker-compose.override.yml` (auto-reload, host ports for Postgres and Qdrant). Add `--watch` to sync backend code changes into the running container.

Or talk to the API directly:

```bash
curl -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"session_id": "demo", "message": "hi! what should I wear on a summer date?"}'
# → {"reply": "..."}
```

Send another message with the same `session_id` to continue the conversation. Health check: `curl localhost:8000/health`.

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
| `MESSAGE_LOG_ENABLED` | `true` | Write every exchange to the `messages` table |

## Project layout

```
zoomerfume/
├── backend/
│   ├── app/
│   │   ├── api/          HTTP routes (health, chat), web chat mount
│   │   ├── agent/        Zoomer: agent runtime, prompt, per-turn context
│   │   ├── core/         settings, logging
│   │   ├── db/           SQLAlchemy engine, models, message log
│   │   ├── middleware/   request logging context
│   │   └── services/     OpenAI and Qdrant clients
│   ├── alembic/          database migrations
│   ├── scripts/          container entrypoint
│   ├── tests/            pytest unit tests
│   └── pyproject.toml    uv project (Python 3.12)
├── frontend/
│   ├── src/              React app: page, components, chat hook, theme
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

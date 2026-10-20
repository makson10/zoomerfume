# Architecture: a chat turn

How Zoomer answers one message: the turn lifecycle, streaming, stopping a reply, the tools, the error envelope, the step cap, citations and conversation history. Retrieval itself (chunking, embeddings, the HNSW index) is in [retrieval.md](retrieval.md).

## The turn

```
POST /api/chat/stream {conversation_id, message}            (POST /api/chat: same turn, one JSON reply)
 1. session cookie → user (401) → rate limit (429) → conversation owner check (404)
 2. start the turn: one running turn per conversation (409)        ── Postgres turns
 3. records the tools returned in earlier turns of this conversation ── Postgres tool_steps
 4. TurnRunner.stream → Runner.run_streamed(agent, message, session, max_turns=5)
      history ── SQLAlchemySession (agent_sessions, agent_messages), last 12 user turns
      ├─ model → search_kb   → embed the query → Qdrant (type / price filters) → envelope
      ├─ model → open_record → kb_records                                     → envelope
      └─ model → final text with [KB-042] citations
      SSE while it runs: tool_call, tool_result, token …
 5. check the citations against the retrieved records
 6. message log, then finish the turn: status, citations, tool steps  ── Postgres messages, turns, tool_steps
 7. SSE: citation, done {turn_id, status, reply}
    the client went away → cancel the run, store the turn as cancelled with the reply so far
```

The route (`app/api/chat.py`) checks the request and starts the turn in the `start_turn` dependency, so a 404 or 409 is a plain JSON error before any event is sent. `TurnRunner.stream()` (`app/agent/runtime.py`) owns the rest of the turn: it runs the agent, yields the turn's events, checks the citations, writes the message log and finishes the turn through `TurnStore` (`app/services/turns.py`). Its last event is the `TurnResult`: the turn id, the reply, the status, the citations and the steps. A turn ends as `ok`, `max_steps` (the step cap was hit), `cancelled` (the customer stopped it) or `failed` (an error or an empty answer, replaced by a fallback text). `POST /api/chat` reads the same stream to the end and returns the `TurnResult`; it always answers 200 with some reply.

## Streaming

`POST /api/chat/stream` answers with server-sent events, through FastAPI's `EventSourceResponse`. `agent_events()` (`app/agent/streaming.py`) turns the Agents SDK's stream events into the turn's events, and the route sends each one as a frame:

| Event | Data | When |
|---|---|---|
| `token` | `{"text": "…"}` | a piece of the reply, as the model writes it |
| `tool_call` | `{"tool": "search_kb", "args": {…}}` | the model called a tool |
| `tool_result` | the step: `{"step", "tool", "args", "success", "code", "record_ids", "duration_ms"}` | the tool finished |
| `citation` | `{"valid": […], "invalid": […], "missing": false}` | the reply is complete |
| `done` | `{"turn_id", "reply", "status"}` | the turn is stored; the last event |
| `error` | `{"code": "INTERNAL_ERROR", "message": "…"}` | the turn broke before it could be stored |

`done` carries the stored reply, and the web chat swaps the streamed text for it. The two are the same for a normal answer. The fallback and step-limit texts are never streamed as tokens, so they arrive only in `done`. A tool's result is the step its `tool_guard` recorded, so the live step log and the stored one match. While the stream is quiet, for example during a tool call, FastAPI sends a `: ping` comment every 15 seconds so proxies keep the connection open. The responses carry `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

```bash
curl -N -b jar -X POST localhost:8000/api/chat/stream \
  -H 'content-type: application/json' -d '{"conversation_id": "<id>", "message": "vanilla under 3000?"}'
# event: tool_call
# data: {"tool":"search_kb","args":{"query":"vanilla perfumes under 3000 UAH","k":5,...}}
#
# event: tool_result
# data: {"step":1,"tool":"search_kb",...,"success":true,"record_ids":["KB-026",...],"duration_ms":1728}
#
# event: token
# data: {"text":"Mary"}
# ...
# event: done
# data: {"turn_id":"...","reply":"Mary, **Maison Margiela Replica Jazz Club** ... [KB-026]","status":"ok"}
```

## One running turn and Stop

A conversation has at most one running turn. Migration `0005` adds a partial unique index on `turns(conversation_id) WHERE status = 'running'`, and `TurnStore.start()` inserts with `ON CONFLICT DO NOTHING`. A second message while Zoomer is still answering, from another tab or a script, gets a 409 `REPLY_IN_PROGRESS` instead of a second run that would mix its items into the same history. The lock lives in Postgres, so it holds across API replicas. If a server dies mid-turn, its turn stays `running`; `start()` first marks running turns older than two minutes as `failed`, so the conversation is blocked for two minutes at most.

The web chat's Stop button aborts the request. FastAPI notices the closed connection and cancels the stream, and `TurnRunner.stream()` then cancels the SDK run and stores the turn as `cancelled` with the tool steps it made. The reply so far stays: in the message log, so the transcript shows it with a "Stopped" note, and in the agent history as an assistant message, so Zoomer knows what it already said. On its own, the SDK keeps only the question and the finished tool calls of a cancelled run. A turn stopped before any text has no reply row. These writes run in a cancelled task, so they are shielded and limited to 5 seconds.

The stored partial reply can end a few words later than the one the browser showed, because tokens already on their way are dropped when the client aborts. A reload shows the stored version.

## Retrieval is a tool

Nothing is retrieved automatically. The model decides when to look something up, and the prompt (`app/agent/prompts.py`) tells it when not to: greetings, small talk, general perfume questions (EDP vs EDT, how to store perfume) and follow-ups that records found earlier in the chat already answer. Everything about the shop itself comes only from the tools. The step log under an answer shows which tools ran, or "No tools used".

| Tool | Arguments | Returns |
|---|---|---|
| `search_kb` | `query`, `k` (1–8, default 5), `record_type` (`product`, `policy`, `company`, `faq`, `news` or null), `max_price` (UAH or null) | `hits`: `record_id`, `title`, `type`, `chunk_index`, `section`, `updated`, `score`, `text`, `price` |
| `open_record` | `record_id`, e.g. `KB-042` | the record's `header` (for products: sizes, prices, availability) and its whole `body` |

Both tools take the run context as their first argument and reach the knowledge base through `TurnContext.kb`, a `KnowledgeBase` (`app/kb/knowledge_base.py`) built once on the app's OpenAI, Qdrant and Postgres clients. The record drawer in the web chat reads the same `kb_records` table through `GET /api/records/{id}`.

## Strict schemas

The SDK builds each tool's JSON schema from its signature and docstring, in strict mode: every property is required (optional ones are nullable) and `additionalProperties` is `false`, so the model's arguments always match the schema, down to the 1–8 range of `k`. `GET /api/tools/schema` returns the schemas straight from the tool objects, and the **Tools** button in the web chat shows them.

## The error envelope

Tools never raise. `tool_guard` (`app/agent/tools/envelope.py`) wraps each one and always returns JSON:

```json
{"success": true, "data": {"hits": [...]}}
{"success": false, "code": "NOT_FOUND", "message": "There is no record KB-999."}
```

| Code | When |
|---|---|
| `INVALID_ARGUMENT` | an empty query, or a record id that doesn't look like `KB-042` |
| `NOT_FOUND` | no record with that id |
| `UPSTREAM_ERROR` | anything else that failed: OpenAI, Qdrant or Postgres |

A tool returns a `ToolResult` (the data and the record ids it came from) or raises `ToolError(code, message)` for an expected failure. Any other exception becomes `UPSTREAM_ERROR` with a fixed message, "The knowledge base is unavailable right now." The exception itself goes only to the log, because the model may repeat a tool's message to the customer. The guard also records every call as a step on the context: tool, arguments, success, code, record ids and duration. The prompt tells Zoomer to say it can't check something when a lookup fails.

## The step cap

`AGENT_MAX_TURNS` (5) caps the model calls per message; one call can request several tools at once. A run that needs more doesn't raise: the SDK's `max_turns` error handler ends it with a polite "I couldn't finish that in 5 steps" answer, which stays in the history, and the turn gets the status `max_steps`.

## Citations

Zoomer cites a record by its id in square brackets right after the fact, e.g. `[KB-026]`. Records refer to each other as plain ids ("see KB-025"), so only bracketed ids count. After the run, `check_citations()` (`app/agent/citations.py`) compares the cited ids with the records the tools returned:

- **valid**: a tool returned the record in this conversation, in this turn or an earlier one. A follow-up answered from records found earlier keeps its citations without a new search.
- **invalid**: no tool returned it in this conversation, so the id was made up or copied from a record's text.
- **missing**: this turn retrieved records, but the answer cites none of them.

Only an answer that finished normally is checked. A `failed` or `max_steps` turn replies with a fixed text that cites nothing, and a `cancelled` reply is unfinished, so they get empty citations and no warning.

The web chat renders each citation as a chip that opens the full record. Invalid ones are red, and the step log flags invalid and missing citations.

## What is stored

| Table | Written by | Holds |
|---|---|---|
| `agent_sessions`, `agent_messages` | the SDK's `SQLAlchemySession` | the conversation history the model sees: messages, tool calls and tool outputs. Created by migration `0004`, not by the SDK |
| `turns` | `TurnStore` | one row per message: status, citations, start and end time; at most one `running` row per conversation |
| `tool_steps` | `TurnStore` | one row per tool call: step number, tool, arguments, success, code, record ids, duration |
| `messages` | the message log | the transcript the web chat shows; each row points to its turn |

The transcript endpoint (`GET /api/conversations/{id}/messages`) returns each of Zoomer's replies with its turn status, citations and steps, so a reloaded chat shows the same chips, step logs and "Stopped" notes. History lives in Postgres, so it survives a restarted or rebuilt `api` container, and any API replica can serve any conversation.

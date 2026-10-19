# Architecture: a chat turn

How Zoomer answers one message: the turn lifecycle, the tools, the error envelope, the step cap, citations and conversation history. Retrieval itself (chunking, embeddings, the HNSW index) is in [retrieval.md](retrieval.md).

## The turn

```
POST /api/chat {conversation_id, message}
 1. session cookie → user (401) → rate limit (429) → conversation owner check (404)
 2. records the tools returned in earlier turns of this conversation  ── Postgres tool_steps
 3. insert turn (status running)                                      ── Postgres turns
 4. TurnRunner.run → Runner.run(agent, message, session, max_turns=5)
      history ── SQLAlchemySession (agent_sessions, agent_messages), last 12 user turns
      ├─ model → search_kb   → embed the query → Qdrant (type / price filters) → envelope
      ├─ model → open_record → kb_records                                     → envelope
      └─ model → final text with [KB-042] citations
 5. check the citations against the retrieved records
 6. finish the turn: status, citations, tool steps                    ── Postgres turns, tool_steps
 7. → {reply, turn_id, citations, steps}
```

The route owns the turn lifecycle (`app/api/chat.py`), with `TurnStore` (`app/services/turns.py`) for the database. `TurnRunner` (`app/agent/runtime.py`) runs the agent and returns a `TurnResult`: the reply, the status and the steps. A turn ends as `ok`, `max_steps` (the step cap was hit) or `failed` (an error or an empty answer, replaced by a fallback text). The endpoint always answers 200 with some reply.

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

Only an answer that finished normally is checked. A `failed` or `max_steps` turn replies with a fixed text that cites nothing, so it gets empty citations and no warning.

The web chat renders each citation as a chip that opens the full record. Invalid ones are red, and the step log flags invalid and missing citations.

## What is stored

| Table | Written by | Holds |
|---|---|---|
| `agent_sessions`, `agent_messages` | the SDK's `SQLAlchemySession` | the conversation history the model sees: messages, tool calls and tool outputs. Created by migration `0004`, not by the SDK |
| `turns` | `TurnStore` | one row per message: status, citations, start and end time |
| `tool_steps` | `TurnStore` | one row per tool call: step number, tool, arguments, success, code, record ids, duration |
| `messages` | the message log | the transcript the web chat shows; each row points to its turn |

The transcript endpoint (`GET /api/conversations/{id}/messages`) returns each of Zoomer's replies with its citations and steps, so a reloaded chat shows the same chips and step logs. History lives in Postgres, so it survives a restarted or rebuilt `api` container, and any API replica can serve any conversation.

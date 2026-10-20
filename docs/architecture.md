# Architecture: a chat turn

How Zoomer answers one message: the turn lifecycle, streaming, stopping a reply, the tools, notes and the bound user id, the error envelope, the step cap, citations, prompt caching, costs and conversation history. Retrieval itself (chunking, embeddings, the HNSW index) is in [retrieval.md](retrieval.md).

## The turn

```
POST /api/chat/stream {conversation_id?, message}           (POST /api/chat: same turn, one JSON reply)
 1. session cookie → user (401) → rate limit (429)
    "/cost"? → the cost report from llm_calls, no model, no turn → SSE: done (see /cost below)
 2. conversation owner check (404), or a new conversation when there is no id ── Postgres conversations
 3. records the tools returned in earlier turns of this conversation ── Postgres tool_steps
 4. start the turn: one running turn per conversation (409)        ── Postgres turns
 5. TurnRunner.stream → Runner.run_streamed(agent + build_tools(user_id), message, session, max_turns=5)
      SSE: start {conversation_id, turn_id}
      history ── SQLAlchemySession (agent_sessions, agent_messages), last 12 user turns
      each model call: [static prompt ◆] [history] [new items] [note: Kyiv time, name]  (◆ cache breakpoint)
      ├─ model → search_kb   → embed the query → Qdrant (type / price filters) → envelope
      ├─ model → open_record → kb_records                                     → envelope
      ├─ model → save_note   → notes, for the user bound in the closure        → envelope
      └─ model → final text with [KB-042] citations
      every model call and search embedding → its usage on the turn's context
      SSE while it runs: tool_call, tool_result, token …
 6. check the citations against the retrieved records
 7. message log, then finish the turn: status, citations, tool steps, model calls
                                       ── Postgres messages, turns, tool_steps, llm_calls
 8. SSE: citation, usage, done {turn_id, status, reply}
    the client went away → cancel the run, store the turn as cancelled with the reply so far
```

The route (`app/api/chat.py`) checks the request and starts the turn in its `start_reply` dependency (`start_turn()`), so a 404 or 409 is a plain JSON error before any event is sent. A message without a `conversation_id` gets a new conversation there, titled after the message. That happens only after the sign-in and rate limit checks, so a refused message leaves no empty chat behind. `TurnRunner.stream()` (`app/agent/runtime.py`) owns the rest of the turn: it runs the agent, yields the turn's events, checks the citations, writes the message log and finishes the turn through `TurnStore` (`app/services/turns.py`). Its first event is a `TurnStart` with the conversation and turn ids, and its last is the `TurnResult`: the conversation and turn ids, the reply, the status, the citations, the steps and the usage. The `TurnStart` comes from inside the runner, so a client that leaves right after it still gets its turn stored as `cancelled`. A turn ends as `ok`, `max_steps` (the step cap was hit), `cancelled` (the customer stopped it) or `failed` (an error or an empty answer, replaced by a fallback text). `POST /api/chat` reads the same stream to the end and returns the `TurnResult`; it always answers 200 with some reply.

## Streaming

`POST /api/chat/stream` answers with server-sent events, through FastAPI's `EventSourceResponse`. `agent_events()` (`app/agent/streaming.py`) turns the Agents SDK's stream events into the turn's events, and the route sends each one as a frame:

| Event | Data | When |
|---|---|---|
| `start` | `{"conversation_id", "turn_id"}` | the turn started; the web chat learns a new conversation's id from it |
| `token` | `{"text": "…"}` | a piece of the reply, as the model writes it |
| `tool_call` | `{"tool": "search_kb", "args": {…}}` | the model called a tool |
| `tool_result` | the step: `{"step", "tool", "args", "success", "code", "record_ids", "duration_ms"}` | the tool finished |
| `citation` | `{"valid": […], "invalid": […], "missing": false}` | the reply is complete |
| `usage` | `{"calls", "input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "cost_usd"}` | the reply is complete; the web chat shows it under the answer |
| `done` | `{"turn_id", "reply", "status"}` | the turn is stored; the last event. `turn_id` is null for a `/cost` reply, which sends only `done` |
| `error` | `{"code": "INTERNAL_ERROR", "message": "…"}` | the turn broke before it could be stored |

The data of every event is a pydantic model, and the route's return type lists them, so the OpenAPI schema describes each payload and the web chat's types are generated from it. `done` carries the stored reply, and the web chat swaps the streamed text for it. The two are the same for a normal answer. The fallback and step-limit texts are never streamed as tokens, so they arrive only in `done`. A tool's result is the step its `tool_guard` recorded, so the live step log and the stored one match. While the stream is quiet, for example during a tool call, FastAPI sends a `: ping` comment every 15 seconds so proxies keep the connection open. The responses carry `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

```bash
curl -N -b jar -X POST localhost:8000/api/chat/stream \
  -H 'content-type: application/json' -d '{"conversation_id": "<id>", "message": "vanilla under 3000?"}'
# event: start
# data: {"conversation_id":"<id>","turn_id":"..."}
#
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

The web chat's Stop button aborts the request, and so does leaving the chat page, for example by logging out. FastAPI notices the closed connection and cancels the stream, and `TurnRunner.stream()` then cancels the SDK run and stores the turn as `cancelled` with the tool steps it made. The reply so far stays: in the message log, so the transcript shows it with a "Stopped" note, and in the agent history as an assistant message, so Zoomer knows what it already said. On its own, the SDK keeps only the question and the finished tool calls of a cancelled run. A turn stopped before any text has no reply row. These writes run in a cancelled task, so they are shielded and limited to 5 seconds.

The stored partial reply can end a few words later than the one the browser showed, because tokens already on their way are dropped when the client aborts. A reload shows the stored version.

## Retrieval is a tool

Nothing is retrieved automatically. The model decides when to look something up, and the prompt (`app/agent/prompts.py`) tells it when not to: greetings, small talk, general perfume questions (EDP vs EDT, how to store perfume) and follow-ups that records found earlier in the chat already answer. Everything about the shop itself comes only from the tools. The step log under an answer shows which tools ran, or "No tools used".

| Tool | Arguments | Returns |
|---|---|---|
| `search_kb` | `query`, `k` (1–8, default 5), `record_type` (`product`, `policy`, `company`, `faq`, `news` or null), `max_price` (UAH or null) | `hits`: `record_id`, `title`, `type`, `chunk_index`, `section`, `updated`, `score`, `text`, `price` |
| `open_record` | `record_id`, e.g. `KB-042` | the record's `header` (for products: sizes, prices, availability) and its whole `body` |

Both tools take the run context as their first argument and reach the knowledge base through `TurnContext.kb`, a `KnowledgeBase` (`app/kb/knowledge_base.py`) built once on the app's OpenAI, Qdrant and Postgres clients. The record drawer in the web chat reads the same `kb_records` table through `GET /api/records/{id}`.

## Strict schemas

The SDK builds each tool's JSON schema from its signature and docstring, in strict mode: every property is required (optional ones are nullable) and `additionalProperties` is `false`, so the model's arguments always match the schema, down to the 1–8 range of `k`. `GET /api/tools/schema` returns the schemas straight from the tools built for the signed-in customer, and the **Tools** button in the web chat shows them.

## Notes and the bound user id

`save_note(text)` saves a short note, such as a wishlist item, for the customer. It is the only tool that writes, and the notes panel in the web chat lists the notes through `GET /api/notes`.

The customer is never an argument. For each turn, `TurnRunner.stream()` runs a copy of the agent with `build_tools(user_id)` (`app/agent/tools/__init__.py`). `make_save_note(user_id)` (`app/agent/tools/save_note.py`) defines `save_note` inside a function, so the tool closes over the id of the customer the session cookie names. `TurnContext` holds no user id, so the closure is the only way the tool knows whose note it writes. The conversation and the turn the note came from do come from the context.

What a model, or anyone else, can do about it:

- The schema has one property, `text`, and `additionalProperties: false`. In strict mode the API makes the model's arguments match the schema, so it can't produce a `user_id`.
- A tool call that carries an extra `user_id` anyway reaches the SDK, which validates the arguments against the function's signature and drops the unknown key. The note still goes to the bound customer; `test_save_note_writes_for_the_user_it_was_built_for` calls the tool exactly that way.
- The schemas don't depend on the customer, so every customer's requests carry identical tool definitions.

`save_note` strips the text and refuses an empty note or one over 500 characters with `INVALID_ARGUMENT`. Otherwise it writes the note through `NoteStore` (`app/services/notes.py`) and returns `{note_id, status: "confirmed"}`. `NoteStore` is built once in the lifespan, and each call opens its own database session, because the tool calls of one model response may run in parallel. Saving only when the customer asks is a rule in the prompt, not a check in code.

## The error envelope

Tools never raise. `tool_guard` (`app/agent/tools/envelope.py`) wraps each one and always returns JSON:

```json
{"success": true, "data": {"hits": [...]}}
{"success": false, "code": "NOT_FOUND", "message": "There is no record KB-999."}
```

| Code | When |
|---|---|
| `INVALID_ARGUMENT` | an empty query, a record id that doesn't look like `KB-042`, or a note that is empty or longer than 500 characters |
| `NOT_FOUND` | no record with that id |
| `UPSTREAM_ERROR` | anything else that failed: OpenAI, Qdrant or Postgres |

A tool returns a `ToolResult` (the data and the record ids it came from) or raises `ToolError(code, message)` for an expected failure. Any other exception becomes `UPSTREAM_ERROR` with a fixed message, "The shop's systems are unavailable right now." The exception itself goes only to the log, because the model may repeat a tool's message to the customer. The guard also records every call as a step on the context: tool, arguments, success, code, record ids and duration. The prompt tells Zoomer to fix its arguments and try once more when the message says how, and otherwise to tell the customer it can't check or save that right now.

## The step cap

`AGENT_MAX_TURNS` (5) caps the model calls per message; one call can request several tools at once. A run that needs more doesn't raise: the SDK's `max_turns` error handler ends it with a polite "I couldn't finish that in 5 steps" answer, which stays in the history, and the turn gets the status `max_steps`.

## Citations

Zoomer cites a record by its id in square brackets right after the fact, e.g. `[KB-026]`. Records refer to each other as plain ids ("see KB-025"), so only bracketed ids count. After the run, `check_citations()` (`app/agent/citations.py`) compares the cited ids with the records the tools returned:

- **valid**: a tool returned the record in this conversation, in this turn or an earlier one. A follow-up answered from records found earlier keeps its citations without a new search.
- **invalid**: no tool returned it in this conversation, so the id was made up or copied from a record's text.
- **missing**: this turn retrieved records, but the answer cites none of them.

Only an answer that finished normally is checked. A `failed` or `max_steps` turn replies with a fixed text that cites nothing, and a `cancelled` reply is unfinished, so they get empty citations and no warning.

The web chat renders each citation as a chip that opens the full record. Invalid ones are red, and the step log flags invalid and missing citations.

## Prompt caching

OpenAI caches the longest prefix a request shares with an earlier request under the same `prompt_cache_key`, and bills those tokens at a tenth of the input price. Writing a prefix to the cache costs 1.25× the input price. So the request has to start with what never changes and end with what always does. `RunConfig.call_model_input_filter` (`cacheable_input()` in `app/agent/input_filter.py`) orders every model call's input:

1. The static prompt, `AGENT_INSTRUCTIONS` (`app/agent/prompts.py`, about 7.9 KB). It is the same for every customer, so it is a constant, not a function of the run. The API rejects an explicit cache breakpoint on the top-level `instructions`, so the filter sends the instructions as the first input item instead: a developer message whose `input_text` block has `prompt_cache_breakpoint: {"mode": "explicit"}`.
2. The history and this turn's items: the customer's message, then the tool calls and outputs of this turn. Retrieved passages are tool outputs, so they come after the static prompt too.
3. A developer note, always the last item: `Now: Tuesday, 20 October 2026, 15:42 Kyiv time. The customer's name is Mary.` The time is taken once per turn (`TurnContext.started_at`), so every call of a turn sends the same note. The shop's rules use Kyiv time and weekdays (courier cutoffs, support hours), so the note gives both.

The filter only shapes what is sent. The SDK stores the history without the static prompt and the note, so the stored items never change. The tool schemas come before the input and don't depend on the customer either.

Caching mode stays `implicit`: next to the explicit breakpoint, OpenAI puts one at the end of the newest user message or tool output. The note sits after it, so it never becomes part of a cached prefix. The next call, in this turn or the next one, reads everything up to that point and writes only what is new. The explicit breakpoint keeps the static prompt cached on its own, which still helps when the history window slides and the prefix after the prompt changes. The request's `prompt_cache_key` is `conversation:<id>`, so a conversation's first call can't read anything and writes the prefix instead, while a second call in the same turn already reads it; `/cost` explains that in a footnote.

## Usage and cost

`UsageHooks` (`app/agent/hooks.py`) is the run's `RunHooks`. Its `on_llm_end` appends one `CallUsage` (`app/services/usage.py`) per chat model call to `TurnContext.calls`: the model, input, cached, cache-write and output tokens, as the Responses API reports them. `search_kb` appends the usage of its query's embedding call, which `KnowledgeBase.search()` returns with the hits. When the turn ends, `TurnStore.finish()` writes them to `llm_calls` with their cost, and the turn's `TurnUsage` goes into the `TurnResult` and the `usage` event. A stopped turn keeps the calls that finished; the call that was cut off never reported its usage. An ingest run writes one `llm_calls` row for its embeddings, with no turn.

`call_cost()` (`app/services/pricing.py`) prices a call from `PRICES`, in USD per million tokens. `input_tokens` already includes the cached and cache-write tokens, so the uncached part is what's left, and each part has its own rate. The math is `Decimal`, rounded to nine places, the scale of `llm_calls.cost_usd`; prices have at most three decimals, so nothing is lost. A model missing from `PRICES` costs 0 with a warning in the log. `TurnUsage` counts the chat model's calls and tokens, and its cost also covers the turn's embeddings. The JSON carries the cost as a plain decimal string, e.g. `"0.000065500"`.

The transcript returns each reply's `usage`, summed per turn by the same `usage_by_turn()` query, so the cost under an answer survives a reload. The web chat shows it as "$0.00047 · 2 calls · 62% cached".

## `/cost`

A message that is exactly `/cost` (any case) is a command, not a question. The route's `start_reply` dependency answers it before any turn starts: `cost_report()` (`app/services/cost_report.py`) builds a Markdown table from the conversation's finished turns and their usage, which `TurnStore.usage_by_turn()` sums from `llm_calls` in one `GROUP BY` query, with one row per turn (time in Kyiv, chat calls, input, cached, cache-write and output tokens, cost), the total, the share of input tokens read from the cache and a footnote on why turn 1 starts with a cache write. No model is called, no turn is stored, and nothing reaches the agent history. The command and the report go to the message log with `kind = command`, so the transcript shows them. That write is fail-open like the rest of the message log (`pg_guard`), so a database hiccup skips it and `/cost` still answers. The stream sends a single `done` with `turn_id: null`; `POST /api/chat` returns the same object. In a new chat there is nothing to count, so `/cost` answers that and creates nothing.

## What is stored

| Table | Written by | Holds |
|---|---|---|
| `agent_sessions`, `agent_messages` | the SDK's `SQLAlchemySession` | the conversation history the model sees: messages, tool calls and tool outputs. Created by migration `0004`, not by the SDK |
| `turns` | `TurnStore` | one row per message: status, citations, start and end time; at most one `running` row per conversation |
| `tool_steps` | `TurnStore` | one row per tool call: step number, tool, arguments, success, code, record ids, duration |
| `messages` | the message log | the transcript the web chat shows; each row points to its turn. `/cost` and its report are rows with `kind = command` and no turn |
| `llm_calls` | `TurnStore`, ingest | one row per model call: chat or embedding, model, input, cached, cache-write and output tokens, cost in USD; the turn it belongs to |
| `notes` | `save_note`, through `NoteStore` | the customer's notes: text, status, the conversation and turn they came from |

The transcript endpoint (`GET /api/conversations/{id}/messages`) returns each of Zoomer's replies with its turn status, citations, steps and usage, so a reloaded chat shows the same chips, step logs, costs and "Stopped" notes. History lives in Postgres, so it survives a restarted or rebuilt `api` container, and any API replica can serve any conversation.

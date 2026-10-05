"""OpenAI Agents SDK runtime.

Owns :class:`TurnRunner`, which produces Zoomer's reply for a single user message,
and the per-session :class:`agents.SQLiteSession` that stores the history.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Runner,
    SQLiteSession,
)
from agents.items import TResponseInputItem
from openai.types.shared import Reasoning
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.context import TurnContext
from app.agent.prompts import AGENT_INSTRUCTIONS
from app.core.config import Settings
from app.db.message_log import record_turn_messages

logger = logging.getLogger(__name__)

# ── SQLite session storage ────────────────────────────────────────────────────
# One file shared across sessions; the session_id keeps conversations isolated.
# The directory is created lazily on first use. The model input is bounded two
# ways: by *age* (RetentionSQLiteSession.get_items below drops turns older than
# `history_retention_days`) and by *count* (`window_history` keeps the last
# `history_window_turns`). Both filter the model input only — nothing is ever
# deleted from the stored session.

_SESSIONS_DIR = Path("data/agents")
_SESSIONS_DB = _SESSIONS_DIR / "sessions.db"


FALLBACK_TEXT = "Oops, something went wrong on my side. Please try again in a minute."


def _agent_instructions(wrapper: RunContextWrapper[TurnContext], agent: Agent) -> str:
    """Per-run system instructions: static base + the current date and time.

    Instructions are recomputed each run and never persisted to the session, so
    the date is always fresh. Appended at the end so the static prefix stays
    cacheable.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    return f"{AGENT_INSTRUCTIONS}\nCurrent date and time: {now} UTC."


class RetentionSQLiteSession(SQLiteSession):
    """SQLiteSession that hides turns older than ``history_retention_days`` from
    the *model input*, while leaving every row on disk.

    The SDK builds the model input by calling ``get_items()`` with no limit (its
    ``SessionSettings.limit`` defaults to ``None``); only that call is
    age-filtered — an explicit ``limit`` or a disabled age cap defers to the
    parent unchanged. The cut is snapped to a turn boundary (see
    :func:`_turn_start_indices`) so a ``function_call`` is never returned without
    its ``function_call_output`` (which would 400 the Responses API).
    """

    def __init__(self, session_id: str, db_path: str, *, retention_days: int) -> None:
        super().__init__(session_id, db_path)
        self.retention_days = retention_days

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        days = self.retention_days
        if limit is not None or days <= 0:
            return await super().get_items(limit)

        def _get_recent_sync() -> list[TResponseInputItem]:
            with self._locked_connection() as conn:
                cursor = conn.execute(
                    f"""
                    SELECT message_data, created_at >= datetime('now', ?) AS within
                    FROM {self.messages_table}
                    WHERE session_id = ?
                    ORDER BY id ASC
                    """,
                    (f"-{days} days", self.session_id),
                )
                rows = cursor.fetchall()

            items: list[TResponseInputItem] = []
            within: list[bool] = []
            for message_data, is_within in rows:
                try:
                    item = json.loads(message_data)
                except (json.JSONDecodeError, TypeError):
                    # Mirror the parent: skip corrupt JSON. Keep items/within aligned
                    # by only appending to both on a successful decode.
                    continue
                items.append(item)
                within.append(bool(is_within))

            starts = _turn_start_indices(items)
            # Earliest turn-start within the window; none → every turn is stale,
            # so feed the model nothing (it starts fresh). Rows stay on disk.
            cut = next((s for s in starts if within[s]), len(items))
            if cut:
                logger.debug(
                    "history age-windowed | items %d -> %d (last %d days)",
                    len(items),
                    len(items) - cut,
                    days,
                )
            return items[cut:]

        return await asyncio.to_thread(_get_recent_sync)


def _is_input_message(item: TResponseInputItem) -> bool:
    """True for a turn-*input* message (a ``user`` / ``developer`` role message).

    Stored Responses items are either role messages (``{"role", "content"}``, no
    ``type``) or tool items (``{"type": "function_call" | "function_call_output"}``,
    no ``role``). Only ``user`` / ``developer`` role messages open a turn; the
    optional ``type == "message"`` form is accepted defensively.
    """
    if not isinstance(item, dict):
        return False
    if item.get("type") not in (None, "message"):
        return False
    return item.get("role") in ("user", "developer")


def _turn_start_indices(history: list[TResponseInputItem]) -> list[int]:
    """Indices in ``history`` where a new user turn begins.

    A turn start is an input message whose predecessor is *not* an input message,
    so a single turn's multi-item input collapses to one boundary. Assistant /
    tool / reasoning items never start a turn — they live *inside* one — so slicing
    at a start index keeps every retained turn (and its tool-call/output pairs)
    whole.
    """
    starts: list[int] = []
    prev_is_input = False
    for i, item in enumerate(history):
        is_input = _is_input_message(item)
        if is_input and not prev_is_input:
            starts.append(i)
        prev_is_input = is_input
    return starts


def window_history(
    history: list[TResponseInputItem],
    new_items: list[TResponseInputItem],
    *,
    turns: int,
) -> list[TResponseInputItem]:
    """Session-input callback: feed the model only the last ``turns`` turns + this turn.

    Bounds per-turn input tokens on long conversations by dropping older turns
    from the *model input* only — the stored session is untouched (the SDK
    persists ``new_items`` regardless). This is the *count* cap; it runs on the
    history already *age*-filtered by :class:`RetentionSQLiteSession`, so the
    model sees turns that are both recent enough and few enough.
    ``turns <= 0`` disables windowing. Cuts strictly on turn boundaries (see
    :func:`_turn_start_indices`), never mid-turn, so a tool-call is never orphaned
    from its output.
    """
    if turns <= 0:
        return history + new_items
    starts = _turn_start_indices(history)
    if len(starts) <= turns:
        return history + new_items
    cut = starts[-turns]
    logger.debug(
        "history windowed | items %d -> %d (last %d turns)", len(history), len(history) - cut, turns
    )
    return history[cut:] + new_items


class TurnRunner:
    """Produces Zoomer's reply for one user message and logs the exchange.

    Created once in the app lifespan and handed to routes through the
    ``get_turn_runner`` dependency.
    """

    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._sessionmaker = sessionmaker
        self._agent = Agent(
            name="Zoomer",
            instructions=_agent_instructions,
            model=settings.chat_model,
            # The chat model doesn't accept `temperature`; low reasoning effort
            # keeps replies quick and consistent.
            model_settings=ModelSettings(reasoning=Reasoning(effort="low")),
        )
        logger.info("Agent created | model=%s", settings.chat_model)

    async def run(self, session_id: str, text: str) -> str:
        """Run one user turn and return Zoomer's reply.

        Any runtime error degrades to :data:`FALLBACK_TEXT`, so the chat never goes
        silent. The exchange is written to the message log after the run.
        """
        ctx = TurnContext(
            session_id=session_id, turn_id=uuid.uuid4().hex, user_message=text.strip()
        )

        try:
            result = await Runner.run(
                self._agent,
                ctx.user_message,
                session=self._session(session_id),
                context=ctx,
                max_turns=self._settings.agent_max_turns,
                run_config=self._run_config(session_id),
            )
            reply = (result.final_output or "").strip()
        except Exception:
            logger.exception("agent run failed | session=%s", session_id)
            reply = ""

        if not reply:
            ctx.degraded = True
            reply = FALLBACK_TEXT
        if self._settings.message_log_enabled:
            await record_turn_messages(self._sessionmaker, ctx, reply)
        return reply

    def _session(self, session_id: str) -> SQLiteSession:
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        return RetentionSQLiteSession(
            session_id, str(_SESSIONS_DB), retention_days=self._settings.history_retention_days
        )

    def _run_config(self, session_id: str) -> RunConfig:
        """Build the run config: history windowing and a ``session:<id>`` prompt cache key.

        The cache key keeps a conversation's turns on one backend, so its prefix stays cached.
        """
        model_settings = ModelSettings(extra_args={"prompt_cache_key": f"session:{session_id}"})
        window = partial(window_history, turns=self._settings.history_window_turns)
        return RunConfig(session_input_callback=window, model_settings=model_settings)

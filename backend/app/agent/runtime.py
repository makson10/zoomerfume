"""OpenAI Agents SDK runtime.

Owns :class:`TurnRunner`, which runs one turn: Zoomer's streamed reply to a single
user message. Each conversation's history lives in Postgres, in an SDK
``SQLAlchemySession``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

import anyio
from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    RunErrorHandlerInput,
    RunErrorHandlerResult,
    Runner,
)
from agents.extensions.memory import SQLAlchemySession
from agents.items import TResponseInputItem
from openai.types.shared import Reasoning
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.agent.citations import Citations, check_citations
from app.agent.context import Step, TurnContext, TurnStatus
from app.agent.hooks import UsageHooks
from app.agent.input_filter import cacheable_input
from app.agent.prompts import AGENT_INSTRUCTIONS
from app.agent.streaming import Token, TurnEvent, agent_events
from app.agent.tools import build_tools
from app.core.config import Settings
from app.core.security import SecurityPolicy
from app.db.guard import WRITE_TIMEOUT_S
from app.db.message_log import record_turn_messages
from app.kb.knowledge_base import KnowledgeBase
from app.services.notes import NoteStore
from app.services.usage import TurnUsage

if TYPE_CHECKING:
    from app.services.turns import TurnStore

logger = logging.getLogger(__name__)

FALLBACK_TEXT = "Oops, something went wrong on my side. Please try again in a minute."
MAX_STEPS_TEXT = (
    "Sorry, I couldn't finish that in {steps} steps. "
    "Could you ask again in a simpler way, or one question at a time?"
)


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
    persists ``new_items`` regardless). ``turns <= 0`` disables windowing. Cuts
    strictly on turn boundaries (see :func:`_turn_start_indices`), never mid-turn,
    so a tool-call is never orphaned from its output.
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


@dataclass(frozen=True)
class NewTurn:
    """A customer's message and the running turn started for it."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    # The signed-in customer, from the session cookie.
    user_id: uuid.UUID
    user_name: str
    message: str
    # The records the tools returned in the conversation's earlier turns.
    retrieved_before: set[str]


class TurnStart(BaseModel):
    """The first event of a turn: the conversation and the turn the reply belongs to."""

    conversation_id: uuid.UUID
    turn_id: uuid.UUID


class TurnResult(BaseModel):
    """Zoomer's reply to one message, with how the turn ended, its checked citations, the
    tool calls behind it and what its model calls cost."""

    conversation_id: uuid.UUID
    turn_id: uuid.UUID
    reply: str
    status: TurnStatus
    citations: Citations
    steps: list[Step]
    usage: TurnUsage


class TurnRunner:
    """Runs Zoomer's turns and stores how they end.

    Created once in the app lifespan and handed to routes through the
    ``get_turn_runner`` dependency.
    """

    def __init__(
        self, settings: Settings, engine: AsyncEngine, kb: KnowledgeBase, notes: NoteStore
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        self._kb = kb
        self._notes = notes
        hardened = settings.security_mode == "hardened"
        self._security = SecurityPolicy(
            untrusted_wrap=hardened
            if settings.harden_untrusted_wrap is None
            else settings.harden_untrusted_wrap,
            rw_separation=hardened
            if settings.harden_rw_separation is None
            else settings.harden_rw_separation,
            confirm_notes=hardened
            if settings.harden_confirm_notes is None
            else settings.harden_confirm_notes,
        )
        # Each turn runs a copy with the customer's own tools.
        self.agent = Agent(
            name="Zoomer",
            instructions=AGENT_INSTRUCTIONS,
            model=settings.chat_model,
            # The chat model doesn't accept `temperature`; low reasoning effort
            # keeps replies quick and consistent.
            model_settings=ModelSettings(reasoning=Reasoning(effort="low")),
        )
        self._hooks = UsageHooks(settings.chat_model)
        logger.info(
            "Agent created | model=%s security=%s", settings.chat_model, self._security.mode
        )

    async def stream(
        self, turn: NewTurn, turns: TurnStore
    ) -> AsyncIterator[TurnStart | TurnEvent | TurnResult]:
        """Run one turn: yield a :class:`TurnStart`, its events as they happen, then its
        :class:`TurnResult`.

        Any runtime error degrades to :data:`FALLBACK_TEXT`, and a run that hits
        ``AGENT_MAX_TURNS`` ends with :data:`MAX_STEPS_TEXT`, so the chat never goes
        silent. Only an answer that finished normally gets its citations checked,
        because those fixed texts cite nothing. The exchange goes to the message log,
        and the turn is stored with its status, citations, tool steps and model calls.

        Closing the stream early (the customer pressed Stop or left) cancels the run.
        The turn is stored as ``cancelled``, and the reply so far is kept in the
        conversation's history and in the message log, so Zoomer knows what it already
        said.

        Args:
            turn: The turn to run. The conversation id is also the SDK session id, so
                each conversation has its own history.
            turns: Where the turn is stored when it ends.
        """
        ctx = TurnContext(
            conversation_id=turn.conversation_id,
            user_name=turn.user_name,
            turn_id=turn.id,
            user_message=turn.message.strip(),
            kb=self._kb,
            notes=self._notes,
            security=self._security,
        )
        agent = self.agent.clone(tools=build_tools(turn.user_id))
        session = self._session(turn.conversation_id)
        result = Runner.run_streamed(
            agent,
            ctx.user_message,
            session=session,
            context=ctx,
            max_turns=self._settings.agent_max_turns,
            run_config=self._run_config(turn.conversation_id),
            error_handlers={"max_turns": self._out_of_steps},
            hooks=self._hooks,
        )
        streamed = ""
        try:
            yield TurnStart(conversation_id=turn.conversation_id, turn_id=turn.id)
            async for event in agent_events(result, ctx.steps):
                if isinstance(event, Token):
                    streamed += event.text
                yield event
            reply = (result.final_output or "").strip()
        except Exception:
            logger.exception("agent run failed | conversation=%s", turn.conversation_id)
            reply = ""
        except (asyncio.CancelledError, GeneratorExit):
            result.cancel()
            # The stream is being cancelled, so the writes need a shield and a time limit.
            with anyio.move_on_after(WRITE_TIMEOUT_S, shield=True):
                await self._store_stopped_turn(ctx, session, turns, streamed.strip())
            raise

        if not reply:
            ctx.status = "failed"
            reply = FALLBACK_TEXT
        citations = Citations()
        if ctx.status == "ok":
            citations = check_citations(reply, ctx.retrieved_ids, turn.retrieved_before)
        if self._settings.message_log_enabled:
            await record_turn_messages(self._sessionmaker, ctx, reply)
        await turns.finish(turn.id, ctx.status, citations, ctx.steps, ctx.calls)
        yield TurnResult(
            conversation_id=turn.conversation_id,
            turn_id=turn.id,
            reply=reply,
            status=ctx.status,
            citations=citations,
            steps=ctx.steps,
            usage=TurnUsage.of(ctx.calls),
        )

    async def _store_stopped_turn(
        self, ctx: TurnContext, session: SQLAlchemySession, turns: TurnStore, reply: str
    ) -> None:
        """Store a stopped turn with its tool steps and finished model calls, and keep the
        reply it wrote so far."""
        logger.info(
            "turn stopped | conversation=%s steps=%d chars=%d",
            ctx.conversation_id,
            len(ctx.steps),
            len(reply),
        )
        try:
            await turns.finish(ctx.turn_id, "cancelled", Citations(), ctx.steps, ctx.calls)
            if reply:
                await session.add_items([{"role": "assistant", "content": reply}])
        except Exception:
            logger.exception("stopped turn not stored | conversation=%s", ctx.conversation_id)
        if self._settings.message_log_enabled:
            await record_turn_messages(self._sessionmaker, ctx, reply)

    def _out_of_steps(self, data: RunErrorHandlerInput[TurnContext]) -> RunErrorHandlerResult:
        """End a run that hit the step limit with a polite answer instead of an error."""
        ctx = data.context.context
        ctx.status = "max_steps"
        logger.warning(
            "agent hit the step limit | conversation=%s steps=%d",
            ctx.conversation_id,
            len(ctx.steps),
        )
        steps = self._settings.agent_max_turns
        return RunErrorHandlerResult(final_output=MAX_STEPS_TEXT.format(steps=steps))

    def _session(self, conversation_id: uuid.UUID) -> SQLAlchemySession:
        return SQLAlchemySession(str(conversation_id), engine=self._engine, ensure_ascii=False)

    def _run_config(self, conversation_id: uuid.UUID) -> RunConfig:
        """Build the run config: history windowing, the cache-friendly input order and a
        ``conversation:<id>`` prompt cache key.

        The cache key gives each conversation its own prompt cache.
        """
        cache_key = f"conversation:{conversation_id}"
        model_settings = ModelSettings(extra_args={"prompt_cache_key": cache_key})
        window = partial(window_history, turns=self._settings.history_window_turns)
        return RunConfig(
            session_input_callback=window,
            call_model_input_filter=cacheable_input,
            model_settings=model_settings,
        )

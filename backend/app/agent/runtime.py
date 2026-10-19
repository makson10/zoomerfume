"""OpenAI Agents SDK runtime.

Owns :class:`TurnRunner`, which produces Zoomer's reply for a single user message.
Each conversation's history lives in Postgres, in an SDK ``SQLAlchemySession``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from functools import partial

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    RunErrorHandlerInput,
    RunErrorHandlerResult,
    Runner,
)
from agents.extensions.memory import SQLAlchemySession
from agents.items import TResponseInputItem
from openai.types.shared import Reasoning
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.agent.context import TurnContext
from app.agent.prompts import AGENT_INSTRUCTIONS
from app.agent.tools import TOOLS
from app.core.config import Settings
from app.db.message_log import record_turn_messages
from app.kb.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

FALLBACK_TEXT = "Oops, something went wrong on my side. Please try again in a minute."
MAX_STEPS_TEXT = (
    "Sorry, I couldn't finish that in {steps} steps. "
    "Could you ask again in a simpler way, or one question at a time?"
)


def _agent_instructions(wrapper: RunContextWrapper[TurnContext], agent: Agent) -> str:
    """Per-run system instructions: static base + the date and time + the customer's name.

    Instructions are recomputed each run and never persisted to the session, so
    the date is always fresh. Appended at the end so the static prefix stays
    cacheable.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    return (
        f"{AGENT_INSTRUCTIONS}\nCurrent date and time: {now} UTC.\n"
        f"The customer's name is {wrapper.context.user_name}."
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


class TurnRunner:
    """Produces Zoomer's reply for one user message and logs the exchange.

    Created once in the app lifespan and handed to routes through the
    ``get_turn_runner`` dependency.
    """

    def __init__(self, settings: Settings, engine: AsyncEngine, kb: KnowledgeBase) -> None:
        self._settings = settings
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        self._kb = kb
        self.agent = Agent(
            name="Zoomer",
            instructions=_agent_instructions,
            model=settings.chat_model,
            tools=TOOLS,
            # The chat model doesn't accept `temperature`; low reasoning effort
            # keeps replies quick and consistent.
            model_settings=ModelSettings(reasoning=Reasoning(effort="low")),
        )
        logger.info("Agent created | model=%s", settings.chat_model)

    async def run(self, conversation_id: uuid.UUID, user_name: str, text: str) -> str:
        """Run one user turn and return Zoomer's reply.

        Any runtime error degrades to :data:`FALLBACK_TEXT`, and a run that hits
        ``AGENT_MAX_TURNS`` ends with :data:`MAX_STEPS_TEXT`, so the chat never goes
        silent. The exchange is written to the message log after the run.

        Args:
            conversation_id: The conversation the turn belongs to. It is also the
                SDK session id, so each conversation has its own history.
            user_name: The signed-in customer's name, for the instructions.
            text: The customer's message.
        """
        ctx = TurnContext(
            conversation_id=conversation_id,
            user_name=user_name,
            turn_id=uuid.uuid4().hex,
            user_message=text.strip(),
            kb=self._kb,
        )

        try:
            result = await Runner.run(
                self.agent,
                ctx.user_message,
                session=self._session(conversation_id),
                context=ctx,
                max_turns=self._settings.agent_max_turns,
                run_config=self._run_config(conversation_id),
                error_handlers={"max_turns": self._out_of_steps},
            )
            reply = (result.final_output or "").strip()
        except Exception:
            logger.exception("agent run failed | conversation=%s", conversation_id)
            reply = ""

        if not reply:
            ctx.degraded = True
            reply = FALLBACK_TEXT
        if self._settings.message_log_enabled:
            await record_turn_messages(self._sessionmaker, ctx, reply)
        return reply

    def _out_of_steps(self, data: RunErrorHandlerInput[TurnContext]) -> RunErrorHandlerResult:
        """End a run that hit the step limit with a polite answer instead of an error."""
        ctx = data.context.context
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
        """Build the run config: history windowing and a ``conversation:<id>`` prompt cache key.

        The cache key keeps a conversation's turns on one backend, so its prefix stays cached.
        """
        cache_key = f"conversation:{conversation_id}"
        model_settings = ModelSettings(extra_args={"prompt_cache_key": cache_key})
        window = partial(window_history, turns=self._settings.history_window_turns)
        return RunConfig(session_input_callback=window, model_settings=model_settings)

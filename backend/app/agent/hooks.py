"""Run hooks: what the agent loop reports about each model call."""

from __future__ import annotations

from agents import Agent, ModelResponse, RunContextWrapper, RunHooks

from app.agent.context import TurnContext
from app.services.usage import CallUsage


class UsageHooks(RunHooks[TurnContext]):
    """Records the token usage of every chat model call on the turn's context."""

    def __init__(self, model: str) -> None:
        self._model = model

    async def on_llm_end(
        self,
        context: RunContextWrapper[TurnContext],
        agent: Agent[TurnContext],
        response: ModelResponse,
    ) -> None:
        usage = response.usage
        context.context.calls.append(
            CallUsage(
                kind="chat",
                model=self._model,
                input_tokens=usage.input_tokens,
                cached_tokens=usage.input_tokens_details.cached_tokens,
                cache_write_tokens=usage.input_tokens_details.cache_write_tokens,
                output_tokens=usage.output_tokens,
            )
        )

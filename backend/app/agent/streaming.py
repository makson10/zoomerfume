"""Turn events: what Zoomer does during a turn, reported while it happens.

:func:`agent_events` turns the Agents SDK's stream events into these events.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agents import RunResultStreaming
from openai.types.responses import ResponseFunctionToolCall, ResponseTextDeltaEvent
from pydantic import BaseModel

from app.agent.context import Step


class Token(BaseModel):
    """A piece of Zoomer's reply, as the model writes it."""

    text: str


class ToolCall(BaseModel):
    """The model called a tool. The tool's result follows as a :class:`Step`."""

    tool: str
    args: dict[str, Any]


# A tool's result is the step the tool guard recorded for it.
TurnEvent = Token | ToolCall | Step


async def agent_events(result: RunResultStreaming, steps: list[Step]) -> AsyncIterator[TurnEvent]:
    """Yield a streamed run's text deltas, tool calls and tool results as turn events.

    Args:
        result: The streamed run.
        steps: The turn's steps, which the tool guard appends to. A step is sent when its
            tool's output shows up in the stream.
    """
    sent = 0
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            yield Token(text=event.data.delta)
        elif event.type == "run_item_stream_event" and event.name == "tool_called":
            call = event.item.raw_item
            if isinstance(call, ResponseFunctionToolCall):
                yield ToolCall(tool=call.name, args=json.loads(call.arguments))
        elif event.type == "run_item_stream_event" and event.name == "tool_output":
            for step in steps[sent:]:
                yield step
            sent = len(steps)

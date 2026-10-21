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

from app.agent.context import PendingNote, Step, TurnContext


class Token(BaseModel):
    """A piece of Zoomer's reply, as the model writes it."""

    text: str


class ToolCall(BaseModel):
    """The model called a tool. The tool's result follows as a :class:`Step`."""

    tool: str
    args: dict[str, Any]


# A tool's result is the step the tool guard recorded for it. A note save_note proposed
# follows its step.
TurnEvent = Token | ToolCall | Step | PendingNote


async def agent_events(result: RunResultStreaming, turn: TurnContext) -> AsyncIterator[TurnEvent]:
    """Yield a streamed run's text deltas, tool calls, tool results and proposed notes as
    turn events.

    Args:
        result: The streamed run.
        turn: The turn's context. The tools append their steps and proposed notes to it,
            and they are sent when a tool's output shows up in the stream.
    """
    sent_steps = sent_notes = 0
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            yield Token(text=event.data.delta)
        elif event.type == "run_item_stream_event" and event.name == "tool_called":
            call = event.item.raw_item
            if isinstance(call, ResponseFunctionToolCall):
                yield ToolCall(tool=call.name, args=json.loads(call.arguments))
        elif event.type == "run_item_stream_event" and event.name == "tool_output":
            for step in turn.steps[sent_steps:]:
                yield step
            for note in turn.pending_notes[sent_notes:]:
                yield note
            sent_steps, sent_notes = len(turn.steps), len(turn.pending_notes)

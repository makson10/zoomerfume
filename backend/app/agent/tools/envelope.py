"""The result envelope every tool returns, and the guard that makes sure of it.

Success is ``{"success": true, "data": {...}}`` and failure is
``{"success": false, "code": "...", "message": "..."}``. Tools never raise.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agents import RunContextWrapper

from app.agent.context import Step, TurnContext

logger = logging.getLogger(__name__)

# The model may repeat a tool's message to the customer, so raw exception text stays in the log.
UPSTREAM_MESSAGE = "The shop's systems are unavailable right now."


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    # A write refused because this turn has read knowledge base text.
    BLOCKED_UNTRUSTED_CONTEXT = "BLOCKED_UNTRUSTED_CONTEXT"


class ToolError(Exception):
    """An expected failure that the model gets as a failure envelope."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolResult:
    """What a tool found: the data for the model and the records it came from."""

    data: dict[str, Any]
    record_ids: list[str] = field(default_factory=list)


def tool_guard(tool: Callable[..., Awaitable[ToolResult]]) -> Callable[..., Awaitable[str]]:
    """Turn a tool's result or error into the JSON envelope and record the call as a step.

    The tool returns a :class:`ToolResult` or raises :class:`ToolError`. Any other
    exception becomes ``UPSTREAM_ERROR`` with a fixed message, so nothing escapes to the
    agent loop.
    """
    signature = inspect.signature(tool)
    arg_names = list(signature.parameters)[1:]

    @functools.wraps(tool)
    async def guarded(ctx: RunContextWrapper[TurnContext], *args: Any, **kwargs: Any) -> str:
        started = time.perf_counter()
        record_ids: list[str] = []
        try:
            result = await tool(ctx, *args, **kwargs)
            record_ids = result.record_ids
            envelope: dict[str, Any] = {"success": True, "data": result.data}
        except ToolError as exc:
            envelope = {"success": False, "code": exc.code, "message": exc.message}
        except Exception:
            logger.exception("tool failed | tool=%s", tool.__name__)
            envelope = {
                "success": False,
                "code": ErrorCode.UPSTREAM_ERROR,
                "message": UPSTREAM_MESSAGE,
            }

        steps = ctx.context.steps
        bound = signature.bind(ctx, *args, **kwargs).arguments
        step = Step(
            step=len(steps) + 1,
            tool=tool.__name__,
            args={name: bound[name] for name in arg_names if name in bound},
            success=envelope["success"],
            code=envelope.get("code"),
            record_ids=record_ids,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        steps.append(step)
        logger.info(
            "tool call | tool=%s success=%s code=%s records=%s ms=%d",
            step.tool,
            step.success,
            step.code,
            ",".join(step.record_ids),
            step.duration_ms,
        )
        return json.dumps(envelope, ensure_ascii=False)

    return guarded

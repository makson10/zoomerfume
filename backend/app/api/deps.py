"""FastAPI dependencies that hand routes the objects built in the app lifespan."""

from __future__ import annotations

from fastapi import Request

from app.agent.runtime import TurnRunner


def get_turn_runner(request: Request) -> TurnRunner:
    """Return the turn runner the lifespan stored on ``app.state``."""
    return request.app.state.turn_runner

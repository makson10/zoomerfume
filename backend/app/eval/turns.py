"""Real turns for the evaluation scripts, run in-process without the HTTP server.

Each question starts a new conversation for a fixed eval customer, so an earlier answer
never reaches the next question. Needs Postgres, Qdrant with an ingested corpus and the
OpenAI API.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.runtime import TurnResult
from app.api.chat import ChatRequest, start_turn
from app.core.config import Settings
from app.main import create_app
from app.services.auth import UserStore
from app.services.conversations import ConversationStore
from app.services.turns import TurnStore

# A fictional number (555-01xx is reserved for fiction), so the eval never signs in as a
# real customer.
EVAL_PHONE = "+15555550142"
EVAL_NAME = "Eval"


@asynccontextmanager
async def running_app(settings: Settings) -> AsyncIterator[FastAPI]:
    """Run the app's lifespan, so its clients, engine and turn runner exist, without
    serving HTTP."""
    # The app's info logs would bury the results. Warnings and errors still show.
    logging.disable(logging.INFO)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


async def ask(app: FastAPI, question: str) -> TurnResult:
    """Ask Zoomer one question in a new conversation of the eval customer and return the
    finished turn."""
    async with app.state.sessionmaker() as session:
        user = await UserStore(session).get_or_create(EVAL_PHONE, EVAL_NAME)
        turns = TurnStore(session)
        turn = await start_turn(
            ChatRequest(message=question),
            user,
            ConversationStore(session),
            turns,
            app.state.settings,
        )
        events = [event async for event in app.state.turn_runner.stream(turn, turns)]
    return events[-1]

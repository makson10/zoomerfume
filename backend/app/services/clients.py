"""Constructors for the OpenAI and Qdrant clients owned by the app lifespan."""

from __future__ import annotations

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient

from app.core.config import Settings


def create_openai_client(settings: Settings) -> AsyncOpenAI:
    """Create the OpenAI client the Agents SDK runs on."""
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=60.0,
        max_retries=settings.openai_max_retries,
    )


def create_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    """Create the Qdrant client."""
    return AsyncQdrantClient(url=settings.qdrant_url, timeout=10)

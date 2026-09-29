"""Shared singleton clients for OpenAI and Qdrant."""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=60.0,
        max_retries=settings.openai_max_retries,
    )


@lru_cache(maxsize=1)
def get_qdrant_client() -> AsyncQdrantClient:
    settings = get_settings()
    return AsyncQdrantClient(url=settings.qdrant_url, timeout=10)


async def close_clients() -> None:
    """Close all shared clients. Call during application shutdown."""
    await get_openai_client().close()
    await get_qdrant_client().close()

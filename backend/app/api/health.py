"""Liveness probe for Docker and monitoring."""

from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

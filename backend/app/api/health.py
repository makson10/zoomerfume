"""Liveness and readiness probes for Docker Compose and Kubernetes, and which replica answered."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.api.deps import AppSettings, ReadinessChecks
from app.middleware.served_by import HOSTNAME

router = APIRouter(tags=["health"])


class ReadinessOut(BaseModel):
    """Whether this replica can serve chat, and each check's result."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


class WhoAmI(BaseModel):
    """The replica that answered and the app version it runs."""

    hostname: str
    version: str


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Liveness: the process is up and answers.

    It checks nothing else, so a Postgres or Qdrant outage never gets the app restarted.
    """
    return {"status": "ok"}


@router.get(
    "/ready",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessOut,
            "description": "A check failed",
        }
    },
)
async def readiness_check(response: Response, readiness: ReadinessChecks) -> ReadinessOut:
    """Readiness: whether this replica can serve chat.

    Postgres must answer, the schema must be at the newest migration and the knowledge
    base must have points. Until all three pass, the answer is a 503.
    """
    checks = await readiness.check()
    if all(result == "ok" for result in checks.values()):
        return ReadinessOut(status="ready", checks=checks)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessOut(status="not_ready", checks=checks)


@router.get("/api/whoami")
async def whoami(settings: AppSettings) -> WhoAmI:
    """Which replica answered: its hostname (the pod name in Kubernetes) and the app version.

    No sign-in needed. Every response also names the replica in ``X-Served-By``.
    """
    return WhoAmI(hostname=HOSTNAME, version=settings.app_version)

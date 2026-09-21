"""Container-orchestrator health endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["platform"])


@router.get("/livez")
def liveness() -> dict[str, str]:
    """Liveness probe: the API process can handle requests."""
    return {"status": "alive"}


@router.get("/healthz")
def readiness() -> dict:
    """Readiness probe: reports configuration needed by the active adapter mode."""
    return {
        "status": "ready",
        "checks": {
            "api": "pass",
            "vector_store": "configured" if os.getenv("QDRANT_URL", "") else "mock",
            "adapter_mode": os.getenv("COPILOT_ADAPTER_MODE", "mock"),
        },
    }

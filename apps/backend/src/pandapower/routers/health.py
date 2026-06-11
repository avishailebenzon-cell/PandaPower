import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    commit: str


# Render injects the deployed commit SHA as RENDER_GIT_COMMIT. Surfacing it on
# /health lets us verify *which* commit is actually live without dashboard
# access (Render auto-deploys have silently lagged before — see Session 38).
_COMMIT = (
    os.getenv("RENDER_GIT_COMMIT")
    or os.getenv("GIT_COMMIT")
    or "unknown"
)[:7]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok", service="pandapower-backend", commit=_COMMIT
    )

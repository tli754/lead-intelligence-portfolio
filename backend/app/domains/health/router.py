"""Health domain router.

Minimal liveness endpoint used to verify the backend skeleton boots. Not
part of any feature's business logic.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def get_health() -> dict[str, str]:
    """Return a static liveness payload."""
    return {"status": "ok"}

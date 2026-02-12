"""Worker health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return worker health status."""
    return {"status": "ok", "service": "elmer-worker"}

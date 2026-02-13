"""Contest endpoints — calendar, live dashboard, band recommendations."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from ..services.contest import get_service

router = APIRouter(prefix="/contest", tags=["contest"])
logger = logging.getLogger("elmer.contest.routes")


@router.get("/upcoming")
async def get_upcoming(
    days: int = Query(default=30, ge=1, le=365, description="Look-ahead days"),
):
    """Upcoming contests in the next N days."""
    svc = get_service()
    contests = await svc.get_upcoming_contests(days=days)
    return [asdict(c) for c in contests]


@router.get("/history")
async def get_contest_history():
    """Historical contest participation from logbook."""
    svc = get_service()
    return await svc.get_contest_history()


@router.get("/recommend-band")
async def recommend_band(
    current_band: str = Query(..., description="Current operating band, e.g. '20m'"),
    contest: str | None = Query(default=None, description="Contest name for context"),
):
    """Band change recommendation based on conditions and contest state."""
    svc = get_service()
    rec = await svc.recommend_band_change(current_band, contest_name=contest)
    return asdict(rec)


@router.get("/{name}")
async def get_contest(name: str):
    """Details for a specific contest by name slug."""
    svc = get_service()
    contest = await svc.get_contest_info(name)
    if contest is None:
        raise HTTPException(status_code=404, detail=f"Contest '{name}' not found")
    return asdict(contest)


@router.get("/{name}/dashboard")
async def get_dashboard(name: str):
    """Live contest dashboard — rates, multipliers, score estimate."""
    svc = get_service()
    try:
        dashboard = await svc.analyze_live_contest(name)
        return asdict(dashboard)
    except Exception as exc:
        logger.warning("Contest dashboard failed for '%s': %s", name, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to build contest dashboard: {exc}",
        )

"""POTA endpoints — park search, spots, activation planning."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from ..services.pota import get_service

router = APIRouter(prefix="/pota", tags=["pota"])
logger = logging.getLogger("elmer.pota.routes")


@router.get("/parks/search")
async def search_parks(
    state: str | None = Query(default=None, description="Location code, e.g. US-CO"),
    name: str | None = Query(default=None, description="Park name substring"),
):
    """Search POTA parks by state/location and optional name filter."""
    svc = get_service()
    parks = await svc.search_parks(state=state, name=name)
    return [asdict(p) for p in parks]


@router.get("/parks/nearby")
async def get_nearby_parks(
    grid: str | None = Query(default=None, description="4-char grid square (default: home grid)"),
    radius: float = Query(default=50.0, ge=1, le=500, description="Radius in miles"),
):
    """Parks near a grid square."""
    svc = get_service()
    parks = await svc.get_nearby_parks(grid=grid, radius_miles=radius)
    return [asdict(p) for p in parks]


@router.get("/park/{reference:path}")
async def get_park(reference: str):
    """Park details by reference (e.g. US-1228)."""
    svc = get_service()
    park = await svc.get_park(reference)
    if park is None:
        raise HTTPException(status_code=404, detail=f"Park '{reference}' not found")
    return asdict(park)


@router.get("/spots")
async def get_spots():
    """Current POTA activator spots."""
    svc = get_service()
    spots = await svc.get_current_spots()
    return [asdict(s) for s in spots]


@router.get("/plan/{reference:path}/bands")
async def get_band_plan(reference: str):
    """Band recommendations for activating a specific park."""
    svc = get_service()
    park = await svc.get_park(reference)
    if park is None:
        raise HTTPException(status_code=404, detail=f"Park '{reference}' not found")
    plan = await svc.plan_activation(reference)
    return {
        "park": reference,
        "recommendations": [asdict(r) for r in plan.band_recommendations],
    }


@router.get("/plan/{reference:path}")
async def plan_activation(reference: str):
    """Comprehensive activation plan for a park."""
    svc = get_service()
    park = await svc.get_park(reference)
    if park is None:
        raise HTTPException(status_code=404, detail=f"Park '{reference}' not found")
    plan = await svc.plan_activation(reference)
    return asdict(plan)

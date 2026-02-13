"""DX cluster endpoints — spots, needs list, entity lookup, cluster status."""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import db
from ..services.callsign_lookup import get_lookup
from ..services.dx_cluster import get_client
from ..services.needs_list import get_needs_list

router = APIRouter(prefix="/dx", tags=["dx"])
logger = logging.getLogger("elmer.dx.routes")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class NeedCreateRequest(BaseModel):
    entity: str
    band: str | None = None
    mode: str | None = None
    priority: int = Field(default=5, ge=1, le=10)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Spots
# ---------------------------------------------------------------------------

@router.get("/spots")
async def get_spots(
    band: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    entity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    since: str | None = Query(default=None, description="ISO timestamp"),
):
    """Recent DX spots with optional filters."""
    conditions = []
    params: list[Any] = []
    idx = 1

    if band:
        conditions.append(f"band = ${idx}")
        params.append(band)
        idx += 1
    if mode:
        conditions.append(f"mode = ${idx}")
        params.append(mode)
        idx += 1
    if entity:
        conditions.append(f"dx_entity ILIKE ${idx}")
        params.append(f"%{entity}%")
        idx += 1
    if since:
        conditions.append(f"timestamp >= ${idx}::timestamptz")
        params.append(since)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = await db.fetch_all(
        f"""
        SELECT id, timestamp, spotter, dx_call, frequency, band, mode,
               comment, dx_entity, raw_spot
        FROM elmer.dx_spots
        {where}
        ORDER BY timestamp DESC
        LIMIT ${idx}
        """,
        *params,
    )

    return [
        {
            "id": r["id"],
            "timestamp": str(r["timestamp"]),
            "spotter": r["spotter"],
            "dx_call": r["dx_call"],
            "frequency": r["frequency"],
            "band": r["band"],
            "mode": r["mode"],
            "comment": r["comment"],
            "dx_entity": r["dx_entity"],
        }
        for r in rows
    ]


@router.get("/spots/summary")
async def get_spots_summary():
    """Band activity summary — spots per band in last hour."""
    rows = await db.fetch_all(
        """
        SELECT band, mode, count(*) AS cnt
        FROM elmer.dx_spots
        WHERE timestamp > now() - interval '1 hour'
        GROUP BY band, mode
        ORDER BY cnt DESC
        """
    )

    bands: dict[str, int] = {}
    modes: dict[str, int] = {}
    for r in rows:
        b = r["band"] or "unknown"
        m = r["mode"] or "unknown"
        bands[b] = bands.get(b, 0) + r["cnt"]
        modes[m] = modes.get(m, 0) + r["cnt"]

    total = await db.fetch_one(
        "SELECT count(*) AS cnt FROM elmer.dx_spots WHERE timestamp > now() - interval '1 hour'"
    )

    client = get_client()
    return {
        "total_last_hour": total["cnt"] if total else 0,
        "bands": bands,
        "modes": modes,
        "cluster_connected": client.get_status()["connected"],
    }


# ---------------------------------------------------------------------------
# Needs list
# ---------------------------------------------------------------------------

@router.get("/needs")
async def get_needs(entity: str | None = Query(default=None)):
    """Current needs list."""
    nl = get_needs_list()
    needs = await nl.get_needs(entity=entity)
    return [
        {
            "id": n.id,
            "entity": n.entity,
            "band": n.band,
            "mode": n.mode,
            "priority": n.priority,
            "notes": n.notes,
            "needed": n.needed,
        }
        for n in needs
    ]


@router.post("/needs", status_code=201)
async def add_need(request: NeedCreateRequest):
    """Add to needs list."""
    nl = get_needs_list()
    result = await nl.add_need(
        entity=request.entity,
        band=request.band,
        mode=request.mode,
        priority=request.priority,
        notes=request.notes,
    )
    return result


@router.delete("/needs/{need_id}")
async def delete_need(need_id: int):
    """Remove from needs list."""
    nl = get_needs_list()
    deleted = await nl.delete_need(need_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Need {need_id} not found")
    return {"id": need_id, "deleted": True}


# ---------------------------------------------------------------------------
# Cluster status
# ---------------------------------------------------------------------------

@router.get("/cluster/status")
async def cluster_status():
    """DX cluster connection status."""
    client = get_client()
    return client.get_status()


# ---------------------------------------------------------------------------
# Entity lookup
# ---------------------------------------------------------------------------

@router.get("/entities/{callsign:path}")
async def lookup_entity(callsign: str):
    """DXCC entity lookup for a callsign."""
    lookup = get_lookup()
    entity = lookup.get_entity(callsign)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"No DXCC entity found for '{callsign}'",
        )
    return {
        "callsign": callsign.upper(),
        "entity_name": entity.entity_name,
        "prefix": entity.prefix,
        "continent": entity.continent,
        "cq_zone": entity.cq_zone,
        "itu_zone": entity.itu_zone,
    }

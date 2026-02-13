"""Home Assistant integration endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..services.homeassistant import get_service

router = APIRouter(prefix="/ha", tags=["homeassistant"])
logger = logging.getLogger("elmer.ha.routes")


@router.get("/states")
async def get_states():
    """All HA entity states grouped by domain."""
    svc = get_service()
    if not svc.configured:
        raise HTTPException(503, "Home Assistant not configured")

    try:
        states = await svc.get_states()
    except Exception as exc:
        raise HTTPException(502, f"Home Assistant unreachable: {exc}")

    # Group by domain.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entity in states:
        domain = entity.get("entity_id", "").split(".")[0]
        grouped.setdefault(domain, []).append({
            "entity_id": entity.get("entity_id"),
            "state": entity.get("state"),
            "friendly_name": entity.get("attributes", {}).get("friendly_name"),
            "last_changed": entity.get("last_changed"),
        })

    return {
        "total_entities": len(states),
        "domains": {k: len(v) for k, v in grouped.items()},
        "entities": grouped,
    }


@router.get("/state/{entity_id:path}")
async def get_state(entity_id: str):
    """Single entity state with full attributes."""
    svc = get_service()
    if not svc.configured:
        raise HTTPException(503, "Home Assistant not configured")

    try:
        state = await svc.get_state(entity_id)
    except Exception as exc:
        raise HTTPException(502, f"Home Assistant unreachable: {exc}")

    if state is None:
        raise HTTPException(404, f"Entity {entity_id} not found")

    return state


@router.get("/history/{entity_id:path}")
async def get_history(entity_id: str, hours: int = Query(24, ge=1, le=168)):
    """State history for an entity over the last N hours."""
    svc = get_service()
    if not svc.configured:
        raise HTTPException(503, "Home Assistant not configured")

    try:
        history = await svc.get_history(entity_id, hours=hours)
    except Exception as exc:
        raise HTTPException(502, f"Home Assistant unreachable: {exc}")

    return history


@router.get("/summary")
async def get_summary():
    """Human-readable home status summary."""
    svc = get_service()
    if not svc.configured:
        raise HTTPException(503, "Home Assistant not configured")

    try:
        summary = await svc.get_summary()
    except Exception as exc:
        raise HTTPException(502, f"Home Assistant unreachable: {exc}")

    return {"summary": summary}


@router.post("/sync")
async def force_sync():
    """Force a knowledge base sync of HA data."""
    svc = get_service()
    if not svc.configured:
        raise HTTPException(503, "Home Assistant not configured")

    result = await svc.sync_to_knowledge_base()
    return result

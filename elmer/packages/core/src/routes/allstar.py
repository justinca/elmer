"""AllStarLink node endpoints — status, connections, remote control."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.allstar import get_service

router = APIRouter(prefix="/allstar", tags=["allstar"])
logger = logging.getLogger("elmer.allstar.routes")


class NodeActionRequest(BaseModel):
    node: int = Field(..., ge=1000, le=999999, description="Remote node number")


@router.get("")
async def get_status(refresh: bool = Query(default=False)):
    """Node status summary — AllStarLink API stats + node info."""
    svc = get_service()
    if refresh:
        svc.clear_cache()
    try:
        status = await svc.get_status()
        return asdict(status)
    except Exception as exc:
        logger.warning("Failed to get AllStar status: %s", exc)
        raise HTTPException(502, f"AllStar status unavailable: {exc}")


@router.get("/stats")
async def get_stats():
    """Raw stats from AllStarLink Stats API."""
    svc = get_service()
    data = await svc.get_raw_stats()
    if data is None:
        raise HTTPException(502, "Could not fetch AllStarLink stats")
    return data


@router.get("/connections")
async def get_connections(refresh: bool = Query(default=False)):
    """Currently connected/linked nodes."""
    svc = get_service()
    if refresh:
        svc.clear_cache()
    connections = await svc.get_connections()
    return [asdict(c) for c in connections]


@router.get("/node/{node_number}")
async def get_node_info(node_number: int):
    """Look up any AllStarLink node from the directory."""
    svc = get_service()
    info = await svc.get_node_info(node_number)
    if info is None:
        raise HTTPException(404, f"Node {node_number} not found in directory")
    return asdict(info)


@router.post("/connect")
async def connect_node(req: NodeActionRequest):
    """Connect to a remote node in transceive mode."""
    svc = get_service()
    result = await svc.connect_node(req.node)
    if result.get("status") == "error":
        raise HTTPException(502, result.get("error", "SSH command failed"))
    return result


@router.post("/disconnect")
async def disconnect_node(req: NodeActionRequest):
    """Disconnect from a remote node."""
    svc = get_service()
    result = await svc.disconnect_node(req.node)
    if result.get("status") == "error":
        raise HTTPException(502, result.get("error", "SSH command failed"))
    return result


@router.post("/monitor")
async def monitor_node(req: NodeActionRequest):
    """Connect to a remote node in monitor (listen-only) mode."""
    svc = get_service()
    result = await svc.monitor_node(req.node)
    if result.get("status") == "error":
        raise HTTPException(502, result.get("error", "SSH command failed"))
    return result

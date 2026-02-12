"""Node registry endpoints."""

import time

import httpx
from fastapi import APIRouter, HTTPException

from ..models.system import NodePingResponse, NodeStatus
from ..services.mqtt_service import node_registry

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[NodeStatus])
async def list_nodes() -> list[NodeStatus]:
    """List all known nodes and their last-seen status."""
    return [
        NodeStatus(
            node_id=node_id,
            name=info.get("name", node_id),
            node_type=info.get("node_type", "unknown"),
            host=info.get("host", ""),
            port=info.get("port", 0),
            status=info.get("status", "unknown"),
            last_seen=info.get("last_seen"),
            metadata=info.get("metadata", {}),
        )
        for node_id, info in node_registry.items()
    ]


@router.post("/{node_id}/ping", response_model=NodePingResponse)
async def ping_node(node_id: str) -> NodePingResponse:
    """Actively ping a node's health endpoint."""
    if node_id not in node_registry:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    info = node_registry[node_id]
    host = info.get("host", "")
    port = info.get("port", 0)

    if not host or not port:
        return NodePingResponse(
            node_id=node_id,
            reachable=False,
            detail="No host/port configured for this node",
        )

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"http://{host}:{port}/health")
            latency = (time.monotonic() - start) * 1000
            reachable = resp.status_code == 200
            return NodePingResponse(
                node_id=node_id,
                reachable=reachable,
                latency_ms=round(latency, 2),
                detail=f"HTTP {resp.status_code}",
            )
    except httpx.RequestError as exc:
        latency = (time.monotonic() - start) * 1000
        return NodePingResponse(
            node_id=node_id,
            reachable=False,
            latency_ms=round(latency, 2),
            detail=str(exc),
        )

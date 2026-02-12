"""Health check endpoints."""

import asyncio
import socket
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from ..models.system import (
    HealthResponse,
    NodeDetailResponse,
    NodeEvent,
    NodeHealth,
    NodeHistoryResponse,
    NodesHealthResponse,
)
from ..services.mqtt_service import node_registry

router = APIRouter(tags=["health"])

# Set at app startup via main.py lifespan.
_start_time: float = 0.0

# NodeMonitor instance — set from main.py lifespan after creation.
_node_monitor: Any = None


def set_start_time(t: float):
    global _start_time
    _start_time = t


def set_node_monitor(monitor: Any):
    global _node_monitor
    _node_monitor = monitor


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return core service status, version, and uptime."""
    uptime = time.time() - _start_time if _start_time else 0.0
    return HealthResponse(
        status="ok",
        service="elmer-core",
        version="0.1.0",
        uptime_seconds=round(uptime, 2),
    )


@router.get("/health/nodes", response_model=NodesHealthResponse)
async def health_nodes() -> NodesHealthResponse:
    """Return all nodes with current status, last heartbeat, and key metrics."""
    results: list[NodeHealth] = []

    # If NodeMonitor is available, use it as the primary source.
    if _node_monitor is not None:
        for node in _node_monitor.get_all_nodes():
            results.append(
                NodeHealth(
                    node_id=node.name,
                    name=node.name,
                    status=node.status,
                    host=node.metadata.get("hostname", ""),
                    port=0,
                    last_seen=node.last_seen,
                    node_type=node.node_type,
                    metadata=node.metadata,
                )
            )
        return NodesHealthResponse(nodes=results)

    # Fallback: use the raw node_registry dict.
    for node_id, info in node_registry.items():
        host = info.get("host", "")
        port = info.get("port", 0)
        status = "unknown"

        if host and port:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                await asyncio.get_event_loop().run_in_executor(
                    None, sock.connect, (host, port)
                )
                sock.close()
                status = "online"
            except (OSError, asyncio.TimeoutError):
                status = "offline"
        else:
            status = info.get("status", "unknown")

        results.append(
            NodeHealth(
                node_id=node_id,
                name=info.get("name", node_id),
                status=status,
                host=host,
                port=port,
                last_seen=info.get("last_seen"),
            )
        )

    return NodesHealthResponse(nodes=results)


@router.get("/health/nodes/{node_id}", response_model=NodeDetailResponse)
async def health_node_detail(node_id: str) -> NodeDetailResponse:
    """Detailed status for a single node."""
    if _node_monitor is not None:
        node = _node_monitor.get_node_status(node_id)
        if node is not None:
            return NodeDetailResponse(
                name=node.name,
                node_type=node.node_type,
                status=node.status,
                last_seen=node.last_seen,
                expected_interval=node.expected_interval,
                metadata=node.metadata,
            )

    # Fallback: check the raw registry.
    if node_id in node_registry:
        info = node_registry[node_id]
        return NodeDetailResponse(
            name=info.get("name", node_id),
            node_type=info.get("node_type", "unknown"),
            status=info.get("status", "unknown"),
            last_seen=info.get("last_seen"),
            metadata=info.get("metadata", {}),
        )

    raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")


@router.get("/health/nodes/{node_id}/history", response_model=NodeHistoryResponse)
async def health_node_history(node_id: str, hours: int = 24) -> NodeHistoryResponse:
    """Recent status history for a node from the events table."""
    if _node_monitor is None:
        raise HTTPException(status_code=503, detail="Node monitor not available")

    # Verify the node exists.
    node = _node_monitor.get_node_status(node_id)
    if node is None and node_id not in node_registry:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    rows = await _node_monitor.get_node_history(node_id, hours=hours)

    events = [
        NodeEvent(
            id=r["id"],
            timestamp=r["timestamp"],
            source=r["source"],
            event_type=r["event_type"],
            data=r.get("data", {}),
        )
        for r in rows
    ]

    return NodeHistoryResponse(node=node_id, events=events)

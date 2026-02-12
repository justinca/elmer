"""Health check endpoints."""

import time

import httpx
from fastapi import APIRouter

from ..models.system import HealthResponse, NodeHealth, NodesHealthResponse
from ..services.mqtt_service import node_registry

router = APIRouter(tags=["health"])

# Set at app startup via main.py lifespan.
_start_time: float = 0.0


def set_start_time(t: float):
    global _start_time
    _start_time = t


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
    """Check health of all registered nodes by hitting their /health endpoints."""
    results: list[NodeHealth] = []

    for node_id, info in node_registry.items():
        host = info.get("host", "")
        port = info.get("port", 0)
        status = "unknown"

        if host and port:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"http://{host}:{port}/health")
                    if resp.status_code == 200:
                        status = "online"
                    else:
                        status = "degraded"
            except httpx.RequestError:
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

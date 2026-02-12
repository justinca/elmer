"""Worker health check endpoint.

Reports worker status, GPU info, Ollama availability, and disk space.
"""

import shutil
import time

import httpx
from fastapi import APIRouter

from ..config import settings
from ..services import gpu_monitor

router = APIRouter(tags=["health"])

_start_time: float = 0.0


def set_start_time(t: float):
    global _start_time
    _start_time = t


async def _check_ollama() -> dict:
    """Ping Ollama and return status."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"status": "online", "models": models}
            return {"status": "degraded", "models": []}
    except httpx.RequestError:
        return {"status": "offline", "models": []}


@router.get("/health")
async def health_check():
    """Return worker status, GPU info, Ollama status, and disk space."""
    uptime = time.time() - _start_time if _start_time else 0.0
    gpu = gpu_monitor.get_gpu_stats()
    ollama = await _check_ollama()

    # Disk space for the drive where the worker is running.
    try:
        disk = shutil.disk_usage(".")
        disk_info = {
            "total_gb": round(disk.total / (1024**3), 1),
            "used_gb": round(disk.used / (1024**3), 1),
            "free_gb": round(disk.free / (1024**3), 1),
        }
    except OSError:
        disk_info = {"total_gb": 0, "used_gb": 0, "free_gb": 0}

    return {
        "status": "ok",
        "service": "elmer-worker",
        "version": "0.1.0",
        "uptime_seconds": round(uptime, 2),
        "gpu": gpu.to_dict(),
        "ollama": ollama,
        "disk": disk_info,
    }

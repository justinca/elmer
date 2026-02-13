"""GPU monitoring via nvidia-smi.

Parses nvidia-smi output and caches results for 5 seconds to avoid
hammering the driver on every health check.
"""

import logging
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger("elmer.worker.gpu")

_cache: "GpuStats | None" = None
_cache_time: float = 0.0
CACHE_TTL = 5.0  # seconds


@dataclass
class GpuStats:
    gpu_name: str
    temperature_c: int
    memory_used_mb: int
    memory_total_mb: int
    utilization_pct: int
    available: bool

    def to_dict(self) -> dict:
        return {
            "gpu_name": self.gpu_name,
            "temperature_c": self.temperature_c,
            "memory_used_mb": self.memory_used_mb,
            "memory_total_mb": self.memory_total_mb,
            "memory_free_mb": self.memory_total_mb - self.memory_used_mb,
            "utilization_pct": self.utilization_pct,
            "available": self.available,
        }


def _query_nvidia_smi() -> GpuStats:
    """Run nvidia-smi and parse CSV output."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("nvidia-smi returned code %d: %s", result.returncode, result.stderr.strip())
            return GpuStats("unknown", 0, 0, 0, 0, available=False)

        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]

        return GpuStats(
            gpu_name=parts[0],
            temperature_c=int(parts[1]),
            memory_used_mb=int(parts[2]),
            memory_total_mb=int(parts[3]),
            utilization_pct=int(parts[4]),
            available=True,
        )
    except FileNotFoundError:
        logger.warning("nvidia-smi not found — no NVIDIA GPU available")
        return GpuStats("none", 0, 0, 0, 0, available=False)
    except Exception:
        logger.exception("Failed to query nvidia-smi")
        return GpuStats("error", 0, 0, 0, 0, available=False)


def get_gpu_stats() -> GpuStats:
    """Return cached GPU stats, refreshing if older than CACHE_TTL."""
    global _cache, _cache_time

    now = time.time()
    if _cache is None or (now - _cache_time) > CACHE_TTL:
        _cache = _query_nvidia_smi()
        _cache_time = now

    return _cache

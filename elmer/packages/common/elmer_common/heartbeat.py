"""Heartbeat manager for Elmer nodes.

Periodically publishes system metrics via MQTT so the Core service
knows every node is alive and healthy.  Works on Linux and Windows.
"""

import asyncio
import logging
import os
import platform
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("elmer.heartbeat")


class HeartbeatManager:
    """Publishes periodic heartbeats over an :class:`ElmerMQTTClient`.

    Parameters
    ----------
    mqtt_client
        An ``ElmerMQTTClient`` instance (must already be connected or
        connecting — heartbeats are silently skipped while disconnected).
    node_name : str
        Identifier for this node (e.g. ``"core"``, ``"worker"``).
    interval : float
        Seconds between heartbeats (default 30).
    """

    def __init__(
        self,
        mqtt_client: Any,  # ElmerMQTTClient — avoid circular import
        node_name: str,
        interval: float = 30.0,
    ) -> None:
        self.mqtt = mqtt_client
        self.node_name = node_name
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._start_time = time.monotonic()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background heartbeat loop."""
        self._start_time = time.monotonic()
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Heartbeat started for '%s' every %.0fs",
            self.node_name, self.interval,
        )

    async def stop(self) -> None:
        """Cancel the background task and publish a final offline beat."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Best-effort offline notification.
        try:
            await self.mqtt.publish_heartbeat(
                self.node_name,
                self._build_payload(status="offline"),
            )
        except Exception:
            pass
        logger.info("Heartbeat stopped for '%s'", self.node_name)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Publish heartbeats forever until cancelled."""
        while True:
            try:
                payload = self._build_payload()
                await self.mqtt.publish_heartbeat(self.node_name, payload)
                logger.debug("Heartbeat sent for '%s'", self.node_name)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Heartbeat publish failed")
            await asyncio.sleep(self.interval)

    def _build_payload(self, status: str = "online") -> dict[str, Any]:
        """Assemble the heartbeat JSON payload."""
        uptime = int(time.monotonic() - self._start_time)
        details = _collect_system_metrics()
        return {
            "node": self.node_name,
            "status": status,
            "uptime_seconds": uptime,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }


# ------------------------------------------------------------------
# Platform-aware system metrics collection
# ------------------------------------------------------------------

def _collect_system_metrics() -> dict[str, Any]:
    """Gather CPU, RAM, disk, and uptime in a cross-platform way."""
    metrics: dict[str, Any] = {
        "platform": platform.system(),
        "hostname": platform.node(),
    }

    try:
        import psutil  # optional dependency
        metrics["cpu_percent"] = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory()
        metrics["ram_total_mb"] = round(mem.total / 1_048_576)
        metrics["ram_used_mb"] = round(mem.used / 1_048_576)
        metrics["ram_percent"] = mem.percent
        disk = psutil.disk_usage("/")
        metrics["disk_total_gb"] = round(disk.total / 1_073_741_824, 1)
        metrics["disk_used_gb"] = round(disk.used / 1_073_741_824, 1)
        metrics["disk_percent"] = disk.percent
    except ImportError:
        # psutil not installed — fall back to basic OS info.
        if platform.system() == "Linux":
            metrics.update(_linux_basic_metrics())
        # On Windows without psutil we just skip detailed metrics.

    # System uptime (not process uptime).
    metrics["system_uptime_seconds"] = _system_uptime()

    return metrics


def _linux_basic_metrics() -> dict[str, Any]:
    """Cheap metrics from /proc when psutil is unavailable."""
    info: dict[str, Any] = {}
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            info["load_1m"] = float(parts[0])
            info["load_5m"] = float(parts[1])
    except OSError:
        pass
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                key, _, val = line.partition(":")
                mem[key.strip()] = int(val.strip().split()[0])  # kB
            total = mem.get("MemTotal", 0)
            avail = mem.get("MemAvailable", 0)
            info["ram_total_mb"] = round(total / 1024)
            info["ram_used_mb"] = round((total - avail) / 1024)
            if total:
                info["ram_percent"] = round((total - avail) / total * 100, 1)
    except (OSError, ValueError, KeyError):
        pass
    return info


def _system_uptime() -> int:
    """Return system uptime in seconds."""
    if platform.system() == "Linux":
        try:
            with open("/proc/uptime") as f:
                return int(float(f.read().split()[0]))
        except OSError:
            pass
    elif platform.system() == "Windows":
        try:
            return int(time.time() - _win_boot_time())
        except Exception:
            pass
    return 0


def _win_boot_time() -> float:
    """Windows boot timestamp via ``psutil`` or ``wmic``."""
    try:
        import psutil
        return psutil.boot_time()
    except ImportError:
        pass
    try:
        import subprocess
        out = subprocess.check_output(
            "wmic os get LastBootUpTime", shell=True, text=True,
        )
        # Output like "20260212081500.000000-360"
        ts = out.strip().split("\n")[-1].strip().split(".")[0]
        from datetime import datetime as _dt
        boot = _dt.strptime(ts, "%Y%m%d%H%M%S")
        return boot.timestamp()
    except Exception:
        return time.time()

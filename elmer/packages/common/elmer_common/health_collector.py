"""Cross-platform system health collector.

Provides ``SystemHealthCollector`` which gathers CPU, RAM, disk, network,
and uptime metrics via *psutil*.  On Linux it also reads CPU temperature;
on Windows it attempts to pull GPU stats from ``nvidia-smi``.
"""

import platform
import subprocess
import time
from typing import Any


class SystemHealthCollector:
    """Collect system health metrics in a standardised dict.

    Designed to be instantiated once and called repeatedly via
    :meth:`collect`.  Keeps minimal state (only the monotonic start
    time for process-uptime calculation).
    """

    def __init__(self) -> None:
        self._start = time.monotonic()

    def collect(self) -> dict[str, Any]:
        """Return a snapshot of current system health."""
        import psutil

        metrics: dict[str, Any] = {
            "platform": platform.system(),
            "hostname": platform.node(),
            "process_uptime_seconds": int(time.monotonic() - self._start),
            "system_uptime_seconds": _system_uptime(),
        }

        # CPU
        metrics["cpu_percent"] = psutil.cpu_percent(interval=0)
        metrics["cpu_count"] = psutil.cpu_count()

        # RAM
        mem = psutil.virtual_memory()
        metrics["ram_total_mb"] = round(mem.total / 1_048_576)
        metrics["ram_used_mb"] = round(mem.used / 1_048_576)
        metrics["ram_percent"] = mem.percent

        # Disk
        disk = psutil.disk_usage("/")
        metrics["disk_total_gb"] = round(disk.total / 1_073_741_824, 1)
        metrics["disk_used_gb"] = round(disk.used / 1_073_741_824, 1)
        metrics["disk_percent"] = disk.percent

        # Network IO (cumulative since boot)
        net = psutil.net_io_counters()
        metrics["net_bytes_sent"] = net.bytes_sent
        metrics["net_bytes_recv"] = net.bytes_recv

        # Platform-specific extras
        if platform.system() == "Linux":
            temp = _linux_cpu_temp()
            if temp is not None:
                metrics["cpu_temp_c"] = temp

        elif platform.system() == "Windows":
            gpu = _windows_gpu_stats()
            if gpu:
                metrics["gpu"] = gpu

        return metrics


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

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
            import psutil
            return int(time.time() - psutil.boot_time())
        except Exception:
            pass
    return 0


def _linux_cpu_temp() -> float | None:
    """Read CPU temperature on Linux via psutil or thermal_zone."""
    try:
        import psutil
        temps = psutil.sensors_temperatures()
        if not temps:
            return _read_thermal_zone()
        # Prefer cpu_thermal (Pi), then coretemp (x86), then first available.
        for key in ("cpu_thermal", "cpu-thermal", "coretemp"):
            if key in temps and temps[key]:
                return round(temps[key][0].current, 1)
        # Fall back to the first sensor found.
        first = next(iter(temps.values()))
        if first:
            return round(first[0].current, 1)
    except Exception:
        pass
    return _read_thermal_zone()


def _read_thermal_zone() -> float | None:
    """Fallback: read /sys/class/thermal/thermal_zone0/temp."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except (OSError, ValueError):
        return None


def _windows_gpu_stats() -> dict[str, Any] | None:
    """Query nvidia-smi for GPU utilisation, memory, and temperature."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
            text=True,
        )
        parts = [p.strip() for p in out.strip().split(",")]
        if len(parts) >= 5:
            return {
                "name": parts[0],
                "gpu_percent": float(parts[1]),
                "vram_used_mb": float(parts[2]),
                "vram_total_mb": float(parts[3]),
                "gpu_temp_c": float(parts[4]),
            }
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass
    return None

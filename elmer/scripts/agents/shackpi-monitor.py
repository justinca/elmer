#!/usr/bin/env python3
"""Elmer ShackPi health monitor agent.

Lightweight script designed to run on the ShackPi (Raspberry Pi) as a
systemd service.  Publishes a heartbeat every 30 seconds via MQTT with:

  - CPU %, RAM %, disk usage, network IO, uptime
  - CPU temperature (critical for Pi thermal management)
  - AllStar/Asterisk service status

Dependencies: paho-mqtt, psutil  (no FastAPI or async frameworks)
"""

import json
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psutil

# ---------------------------------------------------------------------------
# Configuration (from environment or defaults)
# ---------------------------------------------------------------------------
NODE_NAME = os.environ.get("ELMER_NODE_NAME", "shackpi")
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASSWORD", "")
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))

TOPIC_HEARTBEAT = f"elmer/{NODE_NAME}/heartbeat"
TOPIC_STATUS = f"elmer/{NODE_NAME}/status"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(f"elmer.{NODE_NAME}")

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_running = True


def _handle_signal(signum, frame):
    global _running
    logger.info("Received signal %d — shutting down", signum)
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------
_start_time = time.monotonic()


def _cpu_temp() -> float | None:
    """Read CPU temperature on the Raspberry Pi."""
    # Try psutil first (works on most Pis)
    try:
        temps = psutil.sensors_temperatures()
        for key in ("cpu_thermal", "cpu-thermal"):
            if key in temps and temps[key]:
                return round(temps[key][0].current, 1)
    except (AttributeError, Exception):
        pass
    # Fallback: read thermal_zone directly
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except (OSError, ValueError):
        return None


def _service_status(service: str) -> str:
    """Check systemd service status. Returns 'active', 'inactive', etc."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"


def _system_uptime() -> int:
    """System uptime in seconds from /proc/uptime."""
    try:
        with open("/proc/uptime") as f:
            return int(float(f.read().split()[0]))
    except OSError:
        return 0


def collect_metrics() -> dict:
    """Gather all health metrics for the ShackPi."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    metrics = {
        "platform": platform.system(),
        "hostname": platform.node(),
        "cpu_percent": psutil.cpu_percent(interval=0),
        "cpu_count": psutil.cpu_count(),
        "ram_total_mb": round(mem.total / 1_048_576),
        "ram_used_mb": round(mem.used / 1_048_576),
        "ram_percent": mem.percent,
        "disk_total_gb": round(disk.total / 1_073_741_824, 1),
        "disk_used_gb": round(disk.used / 1_073_741_824, 1),
        "disk_percent": disk.percent,
        "net_bytes_sent": net.bytes_sent,
        "net_bytes_recv": net.bytes_recv,
        "system_uptime_seconds": _system_uptime(),
    }

    temp = _cpu_temp()
    if temp is not None:
        metrics["cpu_temp_c"] = temp

    # ShackPi-specific: AllStar/Asterisk
    metrics["services"] = {
        "asterisk": _service_status("asterisk"),
    }

    return metrics


def build_heartbeat(status: str = "online") -> dict:
    """Build the heartbeat MQTT payload."""
    return {
        "node": NODE_NAME,
        "node_type": "shackpi",
        "status": status,
        "uptime_seconds": int(time.monotonic() - _start_time),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": collect_metrics(),
    }


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        logger.info("Connected to MQTT broker at %s:%s", MQTT_HOST, MQTT_PORT)
        # Re-publish online status on every (re)connection so the retained
        # status topic is corrected after the will message fired "offline".
        client.publish(TOPIC_STATUS, json.dumps("online"), retain=True)
        # Send an immediate heartbeat so Core picks up the recovery quickly
        # instead of waiting up to 30s for the next scheduled one.
        try:
            payload = build_heartbeat()
            client.publish(TOPIC_HEARTBEAT, json.dumps(payload, default=str))
            logger.info("Sent recovery heartbeat")
        except Exception:
            logger.debug("Could not send recovery heartbeat", exc_info=True)
    else:
        logger.warning("MQTT connect failed: reason_code=%s", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    logger.warning("Disconnected from MQTT broker (reason_code=%s)", reason_code)


def create_client() -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"elmer-{NODE_NAME}",
    )
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    # Will message: publish offline if we disconnect unexpectedly
    client.will_set(TOPIC_STATUS, json.dumps("offline"), retain=True)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.reconnect_delay_set(min_delay=2, max_delay=60)
    return client


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    logger.info("Starting %s monitor (interval=%ds)", NODE_NAME, HEARTBEAT_INTERVAL)

    client = create_client()

    # Non-blocking connect with automatic reconnect
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    except OSError as exc:
        logger.error("Initial MQTT connect failed: %s — will retry", exc)

    client.loop_start()

    # Prime psutil CPU measurement (first call always returns 0.0)
    psutil.cpu_percent(interval=0)

    try:
        while _running:
            try:
                payload = build_heartbeat()
                msg = json.dumps(payload, default=str)
                result = client.publish(TOPIC_HEARTBEAT, msg)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.debug("Heartbeat sent")
                else:
                    logger.warning("Heartbeat publish returned rc=%d", result.rc)
            except Exception:
                logger.exception("Error building/sending heartbeat")

            # Sleep in small increments so we can respond to signals quickly
            for _ in range(HEARTBEAT_INTERVAL * 10):
                if not _running:
                    break
                time.sleep(0.1)
    finally:
        # Publish offline status before exiting
        logger.info("Publishing offline status and disconnecting")
        client.publish(TOPIC_STATUS, json.dumps("offline"), retain=True)
        offline = build_heartbeat(status="offline")
        client.publish(TOPIC_HEARTBEAT, json.dumps(offline, default=str))
        time.sleep(0.5)  # let messages drain
        client.loop_stop()
        client.disconnect()
        logger.info("%s monitor stopped", NODE_NAME)


if __name__ == "__main__":
    main()

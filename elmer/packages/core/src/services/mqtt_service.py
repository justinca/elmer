"""Core MQTT service — bridges MQTT messages to the node registry and database.

Uses :class:`ElmerMQTTClient` from ``common`` for the actual broker
connection.  On top of that it:

* maintains an in-memory ``node_registry`` updated by heartbeats,
* persists heartbeat events to ``elmer.events``,
* marks nodes as ``"unreachable"`` after 3 missed heartbeat intervals,
* publishes ``elmer/core/status`` retained on connect/disconnect.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from common.src.mqtt import ElmerMQTTClient
from common.src.heartbeat import HeartbeatManager

from ..config import settings
from ..db import connection as db

logger = logging.getLogger("elmer.mqtt")

# ---------------------------------------------------------------------------
# In-memory node registry — keyed by node_id
# ---------------------------------------------------------------------------
node_registry: dict[str, dict[str, Any]] = {}

_DEFAULT_NODES = {
    "worker": {
        "name": "Windows Worker",
        "node_type": "worker",
        "host": settings.ELMER_WORKER_HOST,
        "port": settings.ELMER_WORKER_PORT,
        "status": "unknown",
        "last_seen": None,
        "metadata": {},
    },
    "shackpi": {
        "name": "ShackPi",
        "node_type": "shackpi",
        "host": "",
        "port": 0,
        "status": "unknown",
        "last_seen": None,
        "metadata": {},
    },
    "weatherpi": {
        "name": "WeatherPi",
        "node_type": "weatherpi",
        "host": "",
        "port": 0,
        "status": "unknown",
        "last_seen": None,
        "metadata": {},
    },
}

# How many missed heartbeat intervals before we call a node unreachable.
MISSED_HEARTBEAT_THRESHOLD = 3
# Default heartbeat interval (seconds) — must match HeartbeatManager default.
HEARTBEAT_INTERVAL = 30
# How often to run the staleness checker (seconds).
STALE_CHECK_INTERVAL = 30

# Shared client + heartbeat manager set during lifespan.
_mqtt: ElmerMQTTClient | None = None
_heartbeat: HeartbeatManager | None = None


def _seed_registry() -> None:
    for node_id, info in _DEFAULT_NODES.items():
        if node_id not in node_registry:
            node_registry[node_id] = dict(info)


# ---------------------------------------------------------------------------
# Message handlers (registered as callbacks on ElmerMQTTClient)
# ---------------------------------------------------------------------------

async def _on_heartbeat(topic: str, payload: dict) -> None:
    """Process ``elmer/+/heartbeat`` messages."""
    parts = topic.split("/")
    if len(parts) < 3:
        return
    node_id = parts[1]
    now = datetime.now(timezone.utc)

    if node_id in node_registry:
        node_registry[node_id]["status"] = payload.get("status", "online")
        node_registry[node_id]["last_seen"] = now
        node_registry[node_id]["metadata"] = payload.get("details", {})
    else:
        node_registry[node_id] = {
            "name": payload.get("node", node_id),
            "node_type": payload.get("node_type", "unknown"),
            "host": payload.get("host", ""),
            "port": payload.get("port", 0),
            "status": payload.get("status", "online"),
            "last_seen": now,
            "metadata": payload.get("details", {}),
        }

    logger.debug("Heartbeat from %s: %s", node_id, payload.get("status"))

    # Persist to elmer.events (best-effort, don't block on DB errors).
    await _persist_event(node_id, "heartbeat", payload)


async def _on_status(topic: str, payload: dict) -> None:
    """Process ``elmer/+/status`` messages."""
    parts = topic.split("/")
    if len(parts) < 3:
        return
    node_id = parts[1]
    now = datetime.now(timezone.utc)

    # Status messages may be plain strings wrapped in {"_raw": "online"}.
    status = payload.get("status") or payload.get("_raw", "unknown")
    if isinstance(status, str):
        status = status.strip()

    if node_id in node_registry:
        node_registry[node_id]["status"] = status
        node_registry[node_id]["last_seen"] = now
    else:
        node_registry[node_id] = {
            "name": node_id,
            "node_type": "unknown",
            "host": "",
            "port": 0,
            "status": status,
            "last_seen": now,
            "metadata": {},
        }


async def _on_event(topic: str, payload: dict) -> None:
    """Process ``elmer/events/#`` messages and persist them."""
    source = payload.get("source", "unknown")
    event_type = payload.get("event_type", "unknown")
    await _persist_event(source, event_type, payload.get("data", {}))


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------

async def _persist_event(source: str, event_type: str, data: Any) -> None:
    """Insert a row into ``elmer.events`` if the DB is available."""
    pool = db.get_pool()
    if pool is None:
        return
    try:
        await db.execute(
            "INSERT INTO elmer.events (source, event_type, data) VALUES ($1, $2, $3)",
            source,
            event_type,
            json.dumps(data, default=str),
        )
    except Exception:
        logger.debug("Failed to persist event %s/%s", source, event_type, exc_info=True)


# ---------------------------------------------------------------------------
# Staleness checker
# ---------------------------------------------------------------------------

async def _check_stale_nodes(stop_event: asyncio.Event) -> None:
    """Periodically mark nodes as unreachable if heartbeats stop."""
    timeout = HEARTBEAT_INTERVAL * MISSED_HEARTBEAT_THRESHOLD

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=STALE_CHECK_INTERVAL)
            return  # stop_event was set
        except asyncio.TimeoutError:
            pass

        now = datetime.now(timezone.utc)
        for node_id, info in node_registry.items():
            if node_id == "core":
                continue  # don't mark ourselves
            last = info.get("last_seen")
            if last is None:
                continue
            delta = (now - last).total_seconds()
            if delta > timeout and info["status"] not in ("offline", "unreachable"):
                prev = info["status"]
                info["status"] = "unreachable"
                logger.warning(
                    "Node '%s' unreachable (no heartbeat for %ds, was %s)",
                    node_id, int(delta), prev,
                )
                await _persist_event(
                    "core", "node_unreachable", {"node": node_id, "last_seen": str(last)},
                )
                # Publish event on MQTT as well.
                if _mqtt is not None:
                    await _mqtt.publish_event("core", "node_unreachable", {"node": node_id})


# ---------------------------------------------------------------------------
# Public API (called from main.py lifespan)
# ---------------------------------------------------------------------------

async def publish(topic: str, payload: Any) -> None:
    """Publish a message if the client is connected."""
    if _mqtt is not None:
        await _mqtt.publish(topic, payload)


async def run(stop_event: asyncio.Event) -> None:
    """Start the MQTT client, heartbeat manager, and stale-node checker.

    Blocks until *stop_event* is set.
    """
    global _mqtt, _heartbeat
    _seed_registry()

    _mqtt = ElmerMQTTClient(
        host=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        username=settings.MQTT_USER or None,
        password=settings.MQTT_PASSWORD or None,
        client_id="elmer-core",
    )

    # Register subscription callbacks before connecting.
    _mqtt.subscribe("elmer/+/heartbeat", _on_heartbeat)
    _mqtt.subscribe("elmer/+/status", _on_status)
    _mqtt.subscribe("elmer/events/#", _on_event)

    await _mqtt.connect()

    # Publish retained online status.
    await _mqtt.publish("elmer/core/status", "online", retain=True)

    # Start heartbeat for Core itself.
    _heartbeat = HeartbeatManager(_mqtt, node_name="core", interval=HEARTBEAT_INTERVAL)
    await _heartbeat.start()

    # Start stale-node checker.
    stale_task = asyncio.create_task(_check_stale_nodes(stop_event))

    # Block until shutdown signal.
    await stop_event.wait()

    # Cleanup.
    await _heartbeat.stop()
    stale_task.cancel()
    try:
        await stale_task
    except asyncio.CancelledError:
        pass

    await _mqtt.publish("elmer/core/status", "offline", retain=True)
    await _mqtt.disconnect()
    _mqtt = None
    _heartbeat = None

"""Async MQTT client for Elmer Core.

Subscribes to node heartbeats and status topics, publishes core status.
Handles broker unavailability with retries so the app never crashes.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiomqtt

from ..config import settings

logger = logging.getLogger("elmer.mqtt")

# In-memory node registry updated by MQTT heartbeats.
# Keyed by node_id, values are dicts with status + last_seen.
node_registry: dict[str, dict[str, Any]] = {}

# Pre-populate known nodes so they show up even before first heartbeat.
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

# Shared client reference set during lifespan.
_client: aiomqtt.Client | None = None

RETRY_INTERVAL = 5  # seconds between reconnect attempts


def _seed_registry():
    """Populate registry with default nodes if empty."""
    for node_id, info in _DEFAULT_NODES.items():
        if node_id not in node_registry:
            node_registry[node_id] = dict(info)


def _handle_heartbeat(node_id: str, payload: str):
    """Process a heartbeat message from a node."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        data = {}

    now = datetime.now(timezone.utc)

    if node_id in node_registry:
        node_registry[node_id]["status"] = data.get("status", "online")
        node_registry[node_id]["last_seen"] = now
        node_registry[node_id]["metadata"].update(data.get("metadata", {}))
    else:
        node_registry[node_id] = {
            "name": data.get("name", node_id),
            "node_type": data.get("type", "unknown"),
            "host": data.get("host", ""),
            "port": data.get("port", 0),
            "status": data.get("status", "online"),
            "last_seen": now,
            "metadata": data.get("metadata", {}),
        }

    logger.debug("Heartbeat from %s: %s", node_id, node_registry[node_id]["status"])


def _handle_status(node_id: str, payload: str):
    """Process a status message from a node."""
    now = datetime.now(timezone.utc)
    status = payload.strip() if payload else "unknown"

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


async def publish(topic: str, payload: str):
    """Publish a message if the client is connected."""
    if _client is not None:
        try:
            await _client.publish(topic, payload)
        except aiomqtt.MqttError as exc:
            logger.warning("MQTT publish failed (%s): %s", topic, exc)


async def run(stop_event: asyncio.Event):
    """Main MQTT loop — connects, subscribes, and processes messages.

    Retries on connection failure so the rest of the app stays up.
    Runs until *stop_event* is set.
    """
    global _client
    _seed_registry()

    while not stop_event.is_set():
        try:
            async with aiomqtt.Client(
                hostname=settings.MQTT_HOST,
                port=settings.MQTT_PORT,
            ) as client:
                _client = client
                logger.info(
                    "Connected to MQTT broker at %s:%s",
                    settings.MQTT_HOST,
                    settings.MQTT_PORT,
                )

                await client.publish("elmer/core/status", "online")

                await client.subscribe("elmer/+/heartbeat")
                await client.subscribe("elmer/+/status")

                async for message in client.messages:
                    if stop_event.is_set():
                        break

                    topic_parts = str(message.topic).split("/")
                    payload = (
                        message.payload.decode()
                        if isinstance(message.payload, (bytes, bytearray))
                        else str(message.payload)
                    )

                    # elmer/<node_id>/heartbeat or elmer/<node_id>/status
                    if len(topic_parts) == 3 and topic_parts[0] == "elmer":
                        node_id = topic_parts[1]
                        msg_type = topic_parts[2]

                        if msg_type == "heartbeat":
                            _handle_heartbeat(node_id, payload)
                        elif msg_type == "status":
                            _handle_status(node_id, payload)

        except aiomqtt.MqttError as exc:
            _client = None
            logger.warning(
                "MQTT connection lost (%s), retrying in %ds...",
                exc,
                RETRY_INTERVAL,
            )
        except Exception:
            _client = None
            logger.exception("Unexpected MQTT error, retrying in %ds...", RETRY_INTERVAL)

        # Wait before retry, but respect stop_event.
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RETRY_INTERVAL)
        except asyncio.TimeoutError:
            pass

    # Shutting down — try to publish offline status.
    if _client is not None:
        try:
            await _client.publish("elmer/core/status", "offline")
        except Exception:
            pass
        _client = None

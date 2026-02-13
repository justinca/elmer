"""Meshtastic CalvertCasa channel responder.

Subscribes to the CalvertCasa MQTT topic, passes text messages through
the RAG chat engine, and publishes responses back to the mesh network.

Replaces the Node-RED flow for Meshtastic integration.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings
from . import mqtt_service
from .rag_chat import chat as rag_chat

logger = logging.getLogger("elmer.meshtastic")

# POTA self-spot regex: "POTA US-1228 14050 CW" or "POTA US-1228 14.050 CW"
POTA_SPOT_RE = re.compile(r"^POTA\s+(\S+)\s+(\d+\.?\d*)\s+(\w+)", re.IGNORECASE)

MAX_RESPONSE_BYTES = 200
DEBOUNCE_SECONDS = 10


class MeshtasticService:
    """CalvertCasa channel MQTT handler."""

    def __init__(self) -> None:
        self._debounce: dict[int, float] = {}
        self._message_count: int = 0
        self._last_message_time: datetime | None = None
        self._started: bool = False

    @property
    def configured(self) -> bool:
        return bool(settings.MESHTASTIC_CHANNEL_TOPIC)

    async def start(self) -> None:
        """Subscribe to the CalvertCasa MQTT topic."""
        if self._started:
            return

        topic = settings.MESHTASTIC_CHANNEL_TOPIC
        logger.info("Subscribing to Meshtastic topic: %s", topic)
        await mqtt_service.subscribe_late(topic, self._on_message)
        self._started = True

    def get_status(self) -> dict[str, Any]:
        """Return service status."""
        return {
            "started": self._started,
            "topic": settings.MESHTASTIC_CHANNEL_TOPIC,
            "message_count": self._message_count,
            "last_message": self._last_message_time.isoformat() if self._last_message_time else None,
        }

    async def send_message(self, text: str, channel: int | None = None) -> None:
        """Send a message to the mesh network."""
        payload = {
            "channel": channel if channel is not None else settings.MESHTASTIC_CHANNEL,
            "from": settings.MESHTASTIC_NODE_ID,
            "type": "sendtext",
            "payload": text[:MAX_RESPONSE_BYTES],
        }
        await mqtt_service.publish(
            settings.MESHTASTIC_SEND_TOPIC,
            payload,
        )

    # ------------------------------------------------------------------
    # MQTT callback
    # ------------------------------------------------------------------

    async def _on_message(self, topic: str, payload: dict | str) -> None:
        """Handle incoming Meshtastic messages."""
        # Parse payload if it's a string.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                return

        if not isinstance(payload, dict):
            return

        # Filter: skip non-text messages.
        msg_type = payload.get("type", "")
        if msg_type != "text":
            return

        # Filter: skip messages from the MQTT server itself (echo prevention).
        sender = str(payload.get("from", ""))
        if sender == settings.MESHTASTIC_IGNORE_FROM:
            return

        # Extract text.
        msg_payload = payload.get("payload")
        if isinstance(msg_payload, dict):
            text = msg_payload.get("text", "")
        elif isinstance(msg_payload, str):
            text = msg_payload
        else:
            return

        text = text.strip()
        if not text:
            return

        # Debounce: 10s per sender.
        now = time.monotonic()
        from_id = payload.get("from", 0)
        last = self._debounce.get(from_id, 0)
        if now - last < DEBOUNCE_SECONDS:
            logger.debug("Debounced message from %s", from_id)
            return
        self._debounce[from_id] = now

        self._message_count += 1
        self._last_message_time = datetime.now(timezone.utc)

        rssi = payload.get("rssi", "?")
        snr = payload.get("snr", "?")
        logger.info(
            "Meshtastic message from %s (RSSI:%s SNR:%s): %s",
            from_id, rssi, snr, text[:100],
        )

        # Check for POTA self-spot command.
        pota_match = POTA_SPOT_RE.match(text)
        if pota_match:
            await self._handle_pota_spot(pota_match)
            return

        # All other messages go through RAG chat.
        await self._handle_chat(text)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_pota_spot(self, match: re.Match) -> None:
        """Submit a POTA self-spot and confirm via mesh."""
        park_ref = match.group(1).upper()
        freq = match.group(2)
        mode = match.group(3).upper()

        spot_data = {
            "activator": settings.DX_CLUSTER_CALLSIGN,
            "spotter": settings.DX_CLUSTER_CALLSIGN,
            "frequency": freq,
            "reference": park_ref,
            "mode": mode,
            "source": "elmer-meshtastic",
            "comments": f"Self-spot via Meshtastic",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.pota.app/spot",
                    json=spot_data,
                )
                if resp.status_code in (200, 201):
                    reply = f"POTA spot sent: {park_ref} {freq} {mode}"
                else:
                    reply = f"POTA spot failed ({resp.status_code})"
        except Exception as exc:
            reply = f"POTA spot error: {exc}"
            logger.error("POTA spot failed: %s", exc)

        await self.send_message(reply)

    async def _handle_chat(self, text: str) -> None:
        """Process a text message through RAG chat and respond."""
        # Wrap the message with instructions for short, plain-text response.
        wrapped = (
            f"[Meshtastic: reply under 200 chars, plain text, no markdown, no asterisks] "
            f"{text}"
        )

        try:
            result = await rag_chat(
                message=wrapped,
                channel="meshtastic",
            )
            response = result.response
        except Exception as exc:
            logger.error("RAG chat failed for Meshtastic message: %s", exc)
            response = "Sorry, I couldn't process that right now."

        # Truncate to 200 bytes for Meshtastic.
        encoded = response.encode("utf-8")
        if len(encoded) > MAX_RESPONSE_BYTES:
            encoded = encoded[:MAX_RESPONSE_BYTES - 3]
            # Avoid cutting in the middle of a multi-byte char.
            response = encoded.decode("utf-8", errors="ignore") + "..."

        await self.send_message(response)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_service: MeshtasticService | None = None


def get_service() -> MeshtasticService:
    global _service
    if _service is None:
        _service = MeshtasticService()
    return _service

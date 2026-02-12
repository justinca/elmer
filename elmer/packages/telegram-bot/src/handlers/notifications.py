"""MQTT notification handler — push alerts to Telegram.

Subscribes to heartbeat and event topics, sends notifications when:
- A node goes offline (missed heartbeats / status change)
- A node comes back online
- An event is tagged as "alert" severity
- A new transcription is completed
- Obsidian sync finds new/updated notes

Includes debouncing (aggregate rapid-fire alerts) and quiet-hours
support (less aggressive during sleeping hours).
Notifications are toggleable per-user via /notifications on|off.
"""

import asyncio
import logging
from datetime import datetime

from telegram import Bot
from telegram.ext import Application

from ..config import settings

try:
    from elmer_common.mqtt import ElmerMQTTClient
except ImportError:
    ElmerMQTTClient = None

logger = logging.getLogger("elmer.telegram.notifications")

# Debounce window — batch alerts arriving within this window.
DEBOUNCE_SECS = 30

# During quiet hours, only send critical alerts (node offline).
# Others are queued and sent when quiet hours end, or dropped.
QUIET_BATCH_INTERVAL = 300  # 5 minutes


def _format_duration(seconds: float | None) -> str:
    """Format seconds into Xm Ys."""
    if seconds is None:
        return "?"
    m = int(seconds) // 60
    s = int(seconds) % 60
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


class NotificationManager:
    """Manages MQTT subscriptions and sends Telegram notifications."""

    def __init__(self, bot: Bot, application: Application | None = None) -> None:
        self._bot = bot
        self._application = application
        self._mqtt: ElmerMQTTClient | None = None
        self._node_status: dict[str, str] = {}  # node_id -> last known status
        self._pending_alerts: list[str] = []
        self._debounce_task: asyncio.Task | None = None
        self._flush_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._mqtt_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Connect to MQTT and subscribe to alert topics."""
        if ElmerMQTTClient is None:
            logger.warning(
                "elmer_common not installed — MQTT notifications disabled"
            )
            return

        self._mqtt = ElmerMQTTClient(
            host=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USER or None,
            password=settings.MQTT_PASSWORD or None,
            client_id="elmer-telegram",
        )

        # Subscribe to heartbeats, events, and knowledge topics.
        self._mqtt.subscribe("elmer/+/heartbeat", self._on_heartbeat)
        self._mqtt.subscribe("elmer/events/#", self._on_event)
        self._mqtt.subscribe("elmer/transcription/result", self._on_transcription)
        self._mqtt.subscribe("elmer/knowledge/sync", self._on_knowledge_sync)

        await self._mqtt.connect()
        logger.info("MQTT connected — listening for alerts")

    async def stop(self) -> None:
        """Disconnect cleanly."""
        self._stop_event.set()
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        if self._mqtt:
            await self._mqtt.disconnect()
        # Flush any remaining alerts.
        await self._flush_alerts()

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    async def _on_heartbeat(self, topic: str, payload: dict) -> None:
        """Track node status transitions from heartbeats."""
        parts = topic.split("/")
        if len(parts) < 3:
            return
        node_id = parts[1]
        new_status = payload.get("status", "unknown")
        old_status = self._node_status.get(node_id)

        self._node_status[node_id] = new_status

        if old_status is None:
            # First heartbeat — just record, don't alert.
            return

        if old_status != "offline" and new_status == "offline":
            await self._queue_alert(
                f"\u274c *{node_id}* went offline"
            )

        elif old_status in ("offline", "unreachable") and new_status == "online":
            await self._queue_alert(
                f"\u2705 *{node_id}* is back online"
            )

    async def _on_event(self, topic: str, payload: dict) -> None:
        """Handle events — alert on severity=alert."""
        data = payload.get("data", {})
        severity = data.get("severity", "").lower()
        if severity != "alert":
            return

        source = payload.get("source", "?")
        event_type = payload.get("event_type", "event")
        message = data.get("message", event_type)

        await self._queue_alert(
            f"\u26a0\ufe0f *{source}*: {message}"
        )

    async def _on_transcription(self, topic: str, payload: dict) -> None:
        """Notify when a new transcription is completed."""
        audio_file = payload.get("audio_file", "unknown")
        duration = payload.get("duration_seconds")
        dur_str = _format_duration(duration) if duration else ""

        msg = f"\U0001f3a4 New transcription ready: {audio_file}"
        if dur_str:
            msg += f" ({dur_str})"

        await self._queue_alert(msg)

    async def _on_knowledge_sync(self, topic: str, payload: dict) -> None:
        """Notify when Obsidian sync finds new/updated notes."""
        added = payload.get("added", 0)
        updated = payload.get("updated", 0)
        deleted = payload.get("deleted", 0)

        if added == 0 and updated == 0 and deleted == 0:
            return

        parts = []
        if added:
            parts.append(f"{added} new note{'s' if added != 1 else ''}")
        if updated:
            parts.append(f"{updated} updated")
        if deleted:
            parts.append(f"{deleted} deleted")

        await self._queue_alert(
            f"\U0001f4dd Obsidian sync: {', '.join(parts)}"
        )

    # ------------------------------------------------------------------
    # Alert batching and delivery
    # ------------------------------------------------------------------

    async def _queue_alert(self, message: str) -> None:
        """Add an alert to the pending batch, start debounce timer."""
        self._pending_alerts.append(message)

        # Reset debounce timer.
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        self._debounce_task = asyncio.create_task(
            self._debounce_flush()
        )

    async def _debounce_flush(self) -> None:
        """Wait for the debounce window, then flush."""
        await asyncio.sleep(DEBOUNCE_SECS)
        await self._flush_alerts()

    async def _flush_alerts(self) -> None:
        """Send all pending alerts to authorized Telegram users."""
        async with self._flush_lock:
            if not self._pending_alerts:
                return

            alerts = self._pending_alerts[:]
            self._pending_alerts.clear()

        quiet = self._is_quiet_hours()

        if quiet:
            # During quiet hours, only send node-offline alerts immediately.
            urgent = [a for a in alerts if "\u274c" in a]
            deferred = [a for a in alerts if "\u274c" not in a]

            if urgent:
                text = "\n".join(urgent)
                await self._send_to_all(text)

            if deferred:
                logger.info(
                    "Quiet hours — deferred %d non-critical alerts",
                    len(deferred),
                )
        else:
            if len(alerts) == 1:
                text = alerts[0]
            else:
                text = f"\U0001f514 *{len(alerts)} alerts:*\n\n" + "\n".join(alerts)

            await self._send_to_all(text)

    def _get_muted_users(self) -> set[int]:
        """Get the set of muted user IDs from bot_data."""
        if self._application is not None:
            return self._application.bot_data.get("muted_users", set())
        return set()

    async def _send_to_all(self, text: str) -> None:
        """Send a message to all authorized, non-muted users."""
        muted = self._get_muted_users()
        for user_id in settings.allowed_user_ids:
            if user_id in muted:
                continue
            try:
                await self._bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="Markdown",
                )
            except Exception as exc:
                logger.warning(
                    "Failed to send notification to %s: %s", user_id, exc,
                )

    def _is_quiet_hours(self) -> bool:
        """Check if we're in quiet hours."""
        hour = datetime.now().hour
        start = settings.QUIET_HOURS_START
        end = settings.QUIET_HOURS_END

        if start < end:
            return start <= hour < end
        else:
            # Wraps midnight: 22 <= hour or hour < 7
            return hour >= start or hour < end

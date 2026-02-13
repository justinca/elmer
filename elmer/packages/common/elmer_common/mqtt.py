"""Async MQTT client for Elmer services.

Provides ``ElmerMQTTClient``, a thin wrapper around *aiomqtt* with:

* automatic reconnect using exponential back-off,
* JSON-serialised payloads everywhere,
* convenience publishers for heartbeats and events,
* a callback-based subscription API.

Every Elmer package (core, worker, agents, …) instantiates one client
and shares it across its async tasks.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

import aiomqtt

logger = logging.getLogger("elmer.mqtt")

# Type alias for subscription callbacks.
# Signature: async def handler(topic: str, payload: dict) -> None
MessageCallback = Callable[[str, dict], Awaitable[None]]


class ElmerMQTTClient:
    """Resilient async MQTT client for the Elmer network.

    Parameters
    ----------
    host : str
        Broker hostname or IP.
    port : int
        Broker port (default 1883).
    username : str | None
        Optional broker username.
    password : str | None
        Optional broker password.
    client_id : str
        MQTT client identifier (should be unique per connection).
    topics : list[str] | None
        Topics to subscribe to on (re)connect.
    """

    # Reconnect back-off parameters.
    _BACKOFF_BASE = 2       # seconds
    _BACKOFF_MAX = 60       # cap
    _BACKOFF_FACTOR = 2     # multiplier each failure

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        client_id: str = "elmer",
        topics: list[str] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username or None
        self.password = password or None
        self.client_id = client_id
        self.topics = topics or []

        self._client: aiomqtt.Client | None = None
        self._subscriptions: dict[str, list[MessageCallback]] = {}
        self._stop_event = asyncio.Event()
        self._connected = asyncio.Event()
        self._loop_task: asyncio.Task | None = None
        self._backoff = self._BACKOFF_BASE

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the background connection loop.

        Returns immediately; the loop keeps reconnecting until
        :meth:`disconnect` is called.
        """
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop())
        # Give the first connection attempt a moment.
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("MQTT initial connect still pending — will keep retrying in background.")

    async def disconnect(self) -> None:
        """Signal the connection loop to stop and wait for clean shutdown."""
        self._stop_event.set()
        if self._loop_task is not None:
            try:
                await asyncio.wait_for(self._loop_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._loop_task.cancel()
            self._loop_task = None
        self._client = None
        self._connected.clear()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    # ------------------------------------------------------------------
    # Publish helpers
    # ------------------------------------------------------------------

    async def publish(
        self,
        topic: str,
        payload: Any,
        retain: bool = False,
    ) -> None:
        """Publish a JSON-serialised message.

        *payload* is serialised with ``json.dumps`` before sending.
        If the client is not connected the message is silently dropped
        (home-lab resilience — it will send the next one).
        """
        if self._client is None:
            return
        try:
            raw = json.dumps(payload, default=str)
            await self._client.publish(topic, raw, retain=retain)
        except aiomqtt.MqttError as exc:
            logger.warning("Publish to %s failed: %s", topic, exc)

    async def publish_heartbeat(
        self,
        node_name: str,
        status_data: dict[str, Any],
    ) -> None:
        """Publish a heartbeat to ``elmer/{node_name}/heartbeat``."""
        topic = f"elmer/{node_name}/heartbeat"
        await self.publish(topic, status_data)

    async def publish_event(
        self,
        source: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Publish an event to ``elmer/events/{source}/{event_type}``."""
        payload = {
            "source": source,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        topic = f"elmer/events/{source}/{event_type}"
        await self.publish(topic, payload)

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, callback: MessageCallback) -> None:
        """Register *callback* for messages matching *topic*.

        Must be called **before** :meth:`connect` for the topic to be
        subscribed on the broker.  If called after connect the topic is
        added to the list and will be subscribed on the next reconnect.
        """
        self._subscriptions.setdefault(topic, []).append(callback)
        # Ensure the topic is in the auto-subscribe list.
        if topic not in self.topics:
            self.topics.append(topic)

    async def subscribe_late(self, topic: str, callback: MessageCallback) -> None:
        """Register *callback* AND subscribe on the broker if already connected.

        Use this for subscriptions added after :meth:`connect` has been
        called.  If the client is not yet connected the topic will be
        subscribed on the next (re)connect automatically.
        """
        self.subscribe(topic, callback)
        if self._client is not None:
            try:
                await self._client.subscribe(topic)
                logger.debug("Late-subscribed to %s", topic)
            except aiomqtt.MqttError as exc:
                logger.warning("Late subscribe to %s failed: %s", topic, exc)

    def unsubscribe_callback(self, topic: str, callback: MessageCallback) -> None:
        """Remove a specific *callback* from *topic* subscriptions.

        Does NOT unsubscribe from the broker — the topic remains active
        for other callbacks that may still be registered.
        """
        callbacks = self._subscriptions.get(topic, [])
        try:
            callbacks.remove(callback)
        except ValueError:
            pass
        if not callbacks:
            self._subscriptions.pop(topic, None)

    # ------------------------------------------------------------------
    # Internal — connection loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Maintain the broker connection, dispatching messages."""
        while not self._stop_event.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    identifier=self.client_id,
                ) as client:
                    self._client = client
                    self._connected.set()
                    self._backoff = self._BACKOFF_BASE  # reset on success

                    logger.info(
                        "Connected to MQTT broker at %s:%s as %s",
                        self.host, self.port, self.client_id,
                    )

                    # Subscribe to all registered topics.
                    for topic in self.topics:
                        await client.subscribe(topic)
                        logger.debug("Subscribed to %s", topic)

                    # Message dispatch loop.
                    async for message in client.messages:
                        if self._stop_event.is_set():
                            break
                        await self._dispatch(message)

            except aiomqtt.MqttError as exc:
                self._client = None
                self._connected.clear()
                logger.warning(
                    "MQTT connection lost (%s) — reconnecting in %ds",
                    exc, self._backoff,
                )
            except Exception:
                self._client = None
                self._connected.clear()
                logger.exception(
                    "Unexpected MQTT error — reconnecting in %ds",
                    self._backoff,
                )

            # Exponential back-off wait, but respect stop_event.
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._backoff,
                )
            except asyncio.TimeoutError:
                pass
            self._backoff = min(self._backoff * self._BACKOFF_FACTOR, self._BACKOFF_MAX)

        # Clean exit.
        self._client = None
        self._connected.clear()

    async def _dispatch(self, message: aiomqtt.Message) -> None:
        """Route an incoming message to registered callbacks."""
        topic_str = str(message.topic)
        raw = (
            message.payload.decode()
            if isinstance(message.payload, (bytes, bytearray))
            else str(message.payload)
        )

        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            payload = {"_raw": raw}

        for pattern, callbacks in self._subscriptions.items():
            if _topic_matches(pattern, topic_str):
                for cb in callbacks:
                    try:
                        await cb(topic_str, payload)
                    except Exception:
                        logger.exception(
                            "Error in MQTT callback for %s", topic_str,
                        )


def _topic_matches(pattern: str, topic: str) -> bool:
    """Check whether *topic* matches an MQTT subscription *pattern*.

    Supports ``+`` (single-level) and ``#`` (multi-level) wildcards.
    """
    pat_parts = pattern.split("/")
    top_parts = topic.split("/")

    for i, pat in enumerate(pat_parts):
        if pat == "#":
            return True
        if i >= len(top_parts):
            return False
        if pat != "+" and pat != top_parts[i]:
            return False

    return len(pat_parts) == len(top_parts)

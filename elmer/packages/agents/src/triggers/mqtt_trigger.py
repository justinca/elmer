"""MQTT trigger manager — subscribes to broker topics and fires agent runs."""

import logging
import time
from typing import Any, Callable, Awaitable

from ..models import AgentDefinition

logger = logging.getLogger("elmer.triggers.mqtt")

# Callback type: async def enqueue(agent_name, trigger_type, trigger_data, input_data)
EnqueueCallback = Callable[[str, str, dict, dict], Awaitable[None]]


class MQTTTriggerManager:
    """Watches MQTT topics defined in agent triggers and enqueues runs.

    Features:
    - Wildcard topic support (``+`` and ``#``)
    - Per-agent, per-topic debouncing (default 30 s)
    - Payload filtering (simple key-value matching)
    """

    def __init__(
        self,
        mqtt_client: Any,
        enqueue: EnqueueCallback,
        debounce_default: float = 30.0,
    ) -> None:
        self._mqtt = mqtt_client
        self._enqueue = enqueue
        self._debounce_default = debounce_default
        # (agent_name, actual_topic) -> monotonic timestamp of last trigger
        self._last_triggered: dict[tuple[str, str], float] = {}
        # agent_name -> [(topic_pattern, callback)]  for cleanup
        self._agent_callbacks: dict[str, list[tuple[str, Any]]] = {}
        # Topics already subscribed on broker
        self._subscribed_topics: set[str] = set()

    async def register_agent(self, agent: AgentDefinition) -> int:
        """Register MQTT triggers for *agent*. Returns count registered."""
        count = 0
        callbacks: list[tuple[str, Any]] = []

        for trigger in agent.triggers:
            if trigger.type != "mqtt" or not trigger.topic:
                continue

            topic = trigger.topic
            debounce = trigger.config.get("debounce_seconds", self._debounce_default)
            payload_filter = trigger.payload_filter
            agent_name = agent.name

            # Build a closure that captures this trigger's config.
            async def _handler(
                actual_topic: str,
                payload: dict,
                _name: str = agent_name,
                _pattern: str = topic,
                _filter: dict | None = payload_filter,
                _debounce: float = debounce,
            ) -> None:
                # Payload filter check.
                if _filter and not self._matches_filter(payload, _filter):
                    return

                # Debounce: keyed on (agent_name, actual_topic).
                key = (_name, actual_topic)
                now = time.monotonic()
                last = self._last_triggered.get(key, 0.0)
                if now - last < _debounce:
                    logger.debug(
                        "Debounced %s on %s (%.0fs < %.0fs)",
                        _name, actual_topic, now - last, _debounce,
                    )
                    return
                self._last_triggered[key] = now

                logger.info(
                    "MQTT trigger fired: agent=%s topic=%s pattern=%s",
                    _name, actual_topic, _pattern,
                )

                trigger_data = {
                    "type": "mqtt",
                    "topic": actual_topic,
                    "pattern": _pattern,
                }
                # Pass the full payload as input_data so the agent can use it.
                await self._enqueue(_name, "mqtt", trigger_data, payload)

            # Subscribe (late — broker may already be connected).
            if topic not in self._subscribed_topics:
                await self._mqtt.subscribe_late(topic, _handler)
                self._subscribed_topics.add(topic)
            else:
                # Topic already on broker; just register the callback.
                self._mqtt.subscribe(topic, _handler)

            callbacks.append((topic, _handler))
            count += 1

        self._agent_callbacks[agent.name] = callbacks
        if count:
            logger.info(
                "Registered %d MQTT trigger(s) for '%s'", count, agent.name,
            )
        return count

    def unregister_agent(self, agent_name: str) -> None:
        """Remove all MQTT trigger callbacks for *agent_name*."""
        for topic, callback in self._agent_callbacks.pop(agent_name, []):
            self._mqtt.unsubscribe_callback(topic, callback)

        # Clear debounce entries.
        keys_to_remove = [k for k in self._last_triggered if k[0] == agent_name]
        for k in keys_to_remove:
            del self._last_triggered[k]

    @staticmethod
    def _matches_filter(payload: dict, filter_spec: dict) -> bool:
        """Return True if every key-value pair in *filter_spec* matches *payload*."""
        for key, expected in filter_spec.items():
            if payload.get(key) != expected:
                return False
        return True

"""Event trigger manager — internal event bus via MQTT ``elmer/events/#``."""

import logging
from typing import Any, Callable, Awaitable

from ..models import AgentDefinition

logger = logging.getLogger("elmer.triggers.event")

EnqueueCallback = Callable[[str, str, dict, dict], Awaitable[None]]


class EventTriggerManager:
    """Listens to internal Elmer events (published on ``elmer/events/#``)
    and triggers registered agents.

    Supported event types:
    - ``node_offline`` / ``node_online``
    - ``node_unreachable``
    - ``transcription_complete``
    - ``obsidian_sync_complete``
    - ``agent_run_complete``
    - ``knowledge_ingested``
    - ``system_error``
    """

    def __init__(
        self,
        mqtt_client: Any,
        enqueue: EnqueueCallback,
    ) -> None:
        self._mqtt = mqtt_client
        self._enqueue = enqueue
        # event_type -> [agent_name, ...]
        self._event_agents: dict[str, list[str]] = {}
        self._subscribed = False

    async def start(self) -> None:
        """Subscribe to the events topic on the MQTT broker."""
        if not self._subscribed:
            await self._mqtt.subscribe_late("elmer/events/#", self._on_event)
            self._subscribed = True
            logger.info("Event trigger manager subscribed to elmer/events/#")

    def register_agent(self, agent: AgentDefinition) -> int:
        """Register event triggers for *agent*. Returns count registered."""
        count = 0
        for trigger in agent.triggers:
            if trigger.type != "event" or not trigger.event_type:
                continue
            agents = self._event_agents.setdefault(trigger.event_type, [])
            if agent.name not in agents:
                agents.append(agent.name)
            count += 1
            logger.info(
                "Registered event trigger '%s' for agent '%s'",
                trigger.event_type, agent.name,
            )
        return count

    def unregister_agent(self, agent_name: str) -> None:
        """Remove *agent_name* from all event subscriptions."""
        for event_type in list(self._event_agents):
            agents = self._event_agents[event_type]
            self._event_agents[event_type] = [a for a in agents if a != agent_name]
            if not self._event_agents[event_type]:
                del self._event_agents[event_type]

    async def _on_event(self, topic: str, payload: dict) -> None:
        """MQTT callback for ``elmer/events/#`` messages."""
        # Extract event_type: prefer payload field, fallback to topic path.
        event_type = payload.get("event_type", "")
        if not event_type:
            # elmer/events/{source}/{event_type} → last segment
            parts = topic.split("/")
            event_type = parts[-1] if len(parts) >= 4 else ""

        if not event_type:
            return

        agent_names = self._event_agents.get(event_type, [])
        if not agent_names:
            return

        source = payload.get("source", "")
        event_data = payload.get("data", {})
        if isinstance(event_data, str):
            event_data = {"_raw": event_data}

        for agent_name in agent_names:
            logger.info(
                "Event trigger fired: agent=%s event=%s source=%s",
                agent_name, event_type, source,
            )
            trigger_data: dict[str, Any] = {
                "type": "event",
                "event_type": event_type,
                "source": source,
                "topic": topic,
            }
            await self._enqueue(agent_name, "event", trigger_data, event_data)

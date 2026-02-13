"""Core-side orchestrator — wires the AgentOrchestrator into core services."""

import logging
from typing import Any

from elmer_agents.orchestrator import AgentOrchestrator
from elmer_agents.registry import AgentRegistry

from .agent_executor import get_executor
from .mqtt_service import get_client, publish as mqtt_publish
from . import db

logger = logging.getLogger("elmer.orchestrator")

_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator | None:
    """Return the running orchestrator instance (``None`` before start)."""
    return _orchestrator


async def start_orchestrator() -> AgentOrchestrator:
    """Create and start the agent orchestrator.

    Must be called after MQTT is connected and agent definitions are synced.
    """
    global _orchestrator

    mqtt_client = get_client()
    if mqtt_client is None:
        raise RuntimeError("MQTT client not available — cannot start orchestrator")

    registry = AgentRegistry(db)
    executor = get_executor()

    _orchestrator = AgentOrchestrator(
        registry=registry,
        executor=executor,
        mqtt_client=mqtt_client,
        mqtt_publish=mqtt_publish,
        db=db,
    )

    await _orchestrator.start()
    return _orchestrator


async def stop_orchestrator() -> None:
    """Gracefully shut down the orchestrator."""
    global _orchestrator
    if _orchestrator is not None:
        await _orchestrator.stop()
        _orchestrator = None

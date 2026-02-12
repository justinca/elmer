"""Core-side agent executor — wires the agents package executor into core services."""

import json
import logging
from typing import Any

from elmer_agents.executor import AgentExecutor
from elmer_agents.models import AgentDefinition, AgentTool, AgentTrigger

from ..config import settings
from . import db
from .mqtt_service import publish as mqtt_publish

logger = logging.getLogger("elmer.agent_executor")

_executor: AgentExecutor | None = None


def get_executor() -> AgentExecutor:
    """Return the singleton AgentExecutor wired to core's live services."""
    global _executor
    if _executor is None:
        _executor = AgentExecutor(
            db=db,
            settings=settings,
            mqtt_publish=mqtt_publish,
        )
    return _executor


async def execute_agent_run(
    agent_row: dict[str, Any],
    run_id: int,
    input_data: dict[str, Any],
) -> None:
    """Background task — called from the route handler via asyncio.create_task().

    Converts the raw database row to an AgentDefinition, then runs
    the executor. All exceptions are caught and recorded.
    """
    executor = get_executor()
    agent_def = _row_to_agent_definition(agent_row)

    try:
        result = await executor.execute(
            agent_def, run_id, trigger_data={}, input_data=input_data,
        )
        status = "completed" if "error" not in result else result.get("status", "failed")
        logger.info(
            "Agent '%s' run %d finished: %s (%d steps)",
            agent_def.name, run_id, status,
            result.get("steps", 0),
        )
    except Exception:
        logger.exception("Agent '%s' run %d crashed", agent_def.name, run_id)


def _row_to_agent_definition(row: dict[str, Any]) -> AgentDefinition:
    """Convert an asyncpg row (as dict) to an AgentDefinition."""

    def _parse_json(val: Any) -> Any:
        if val is None:
            return None
        if isinstance(val, str):
            return json.loads(val)
        return val

    raw_tools = _parse_json(row.get("tools")) or []
    raw_triggers = _parse_json(row.get("triggers")) or []
    raw_channels = _parse_json(row.get("output_channels")) or []
    raw_config = _parse_json(row.get("config")) or {}

    tools = [
        AgentTool(**t) if isinstance(t, dict) else AgentTool(name=str(t))
        for t in raw_tools
    ]
    triggers = [
        AgentTrigger(**t) for t in raw_triggers if isinstance(t, dict)
    ]

    return AgentDefinition(
        id=row.get("id"),
        name=row["name"],
        display_name=row.get("display_name") or "",
        description=row.get("description") or "",
        system_prompt=row.get("system_prompt") or "",
        model=row.get("model") or "llama3.1:8b",
        tools=tools,
        triggers=triggers,
        output_channels=raw_channels if isinstance(raw_channels, list) else [],
        config=raw_config,
        enabled=row.get("enabled", True),
        max_concurrent=row.get("max_concurrent", 1),
        timeout_seconds=row.get("timeout_seconds", 120),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )

"""Agent management endpoints — CRUD for agent definitions and run history."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import db

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger("elmer.agents")


# ---------------------------------------------------------------------------
# Pydantic models (mirrors packages/agents/src/models.py for the API layer)
# ---------------------------------------------------------------------------


class AgentTool(BaseModel):
    name: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class AgentTrigger(BaseModel):
    type: str
    topic: str | None = None
    payload_filter: dict[str, Any] | None = None
    cron: str | None = None
    interval_seconds: int | None = None
    event_type: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class AgentDefinitionResponse(BaseModel):
    id: int
    name: str
    display_name: str = ""
    description: str = ""
    system_prompt: str = ""
    model: str = "llama3.1:8b"
    tools: list[AgentTool] = Field(default_factory=list)
    triggers: list[AgentTrigger] = Field(default_factory=list)
    output_channels: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    max_concurrent: int = 1
    timeout_seconds: int = 120
    created_at: str | None = None
    updated_at: str | None = None


class AgentCreateRequest(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
    display_name: str = ""
    description: str = ""
    system_prompt: str = ""
    model: str = "llama3.1:8b"
    tools: list[AgentTool] = Field(default_factory=list)
    triggers: list[AgentTrigger] = Field(default_factory=list)
    output_channels: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    max_concurrent: int = 1
    timeout_seconds: int = 120


class AgentUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    tools: list[AgentTool] | None = None
    triggers: list[AgentTrigger] | None = None
    output_channels: list[str] | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    max_concurrent: int | None = None
    timeout_seconds: int | None = None


class AgentRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    id: int
    agent_id: int
    agent_name: str = ""
    trigger_type: str
    trigger_data: dict[str, Any] = Field(default_factory=dict)
    status: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    error: str | None = None


class AgentRunSummary(BaseModel):
    id: int
    agent_name: str
    trigger_type: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, str):
        return json.loads(val)
    return val


def _row_to_response(row) -> AgentDefinitionResponse:
    raw_tools = _parse_json(row.get("tools")) or []
    raw_triggers = _parse_json(row.get("triggers")) or []
    raw_channels = _parse_json(row.get("output_channels")) or []
    raw_config = _parse_json(row.get("config")) or {}

    tools = [AgentTool(**t) if isinstance(t, dict) else AgentTool(name=str(t)) for t in raw_tools]
    triggers = [AgentTrigger(**t) for t in raw_triggers if isinstance(t, dict)]

    return AgentDefinitionResponse(
        id=row["id"],
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
        created_at=str(row["created_at"]) if row.get("created_at") else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
    )


def _row_to_run(row) -> AgentRunResponse:
    return AgentRunResponse(
        id=row["id"],
        agent_id=row["agent_id"],
        agent_name=row.get("agent_name", ""),
        trigger_type=row.get("trigger_type", ""),
        trigger_data=_parse_json(row.get("trigger_data")) or {},
        status=row.get("status", ""),
        input_data=_parse_json(row.get("input_data")) or {},
        output_data=_parse_json(row.get("output_data")) or {},
        started_at=str(row["started_at"]) if row.get("started_at") else None,
        completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
        duration_seconds=row.get("duration_seconds"),
        error=row.get("error"),
    )


def _reload_agent_triggers(name: str) -> None:
    """Tell the orchestrator to re-read an agent's triggers (fire-and-forget)."""
    from ..services.orchestrator_service import get_orchestrator

    orch = get_orchestrator()
    if orch is not None:
        asyncio.create_task(orch.reload_agent(name))


# ---------------------------------------------------------------------------
# YAML sync — called on startup from main.py
# ---------------------------------------------------------------------------


async def sync_agent_definitions(definitions_dir: str | Path) -> dict[str, int]:
    """Load YAML agent definitions and upsert into the database.

    Called once on Core startup to ensure DB has the latest definitions.
    """
    path = Path(definitions_dir)
    if not path.is_dir():
        logger.warning("Agent definitions directory not found: %s", path)
        return {"registered": 0, "updated": 0, "skipped": 0, "errors": 0}

    counts = {"registered": 0, "updated": 0, "skipped": 0, "errors": 0}

    for yaml_file in sorted(path.glob("*.yaml")):
        try:
            with yaml_file.open() as f:
                data = yaml.safe_load(f)

            name = data["name"]

            # Normalize tools and triggers to JSON-serializable dicts.
            raw_tools = data.get("tools", [])
            tools = []
            for t in raw_tools:
                if isinstance(t, str):
                    tools.append({"name": t, "description": "", "config": {}})
                elif isinstance(t, dict):
                    tools.append(t)

            raw_triggers = data.get("triggers", [])

            # Check if agent already exists.
            existing = await db.fetch_one(
                "SELECT id, system_prompt, description, triggers FROM elmer.agent_definitions WHERE name = $1",
                name,
            )

            if existing is None:
                await db.execute(
                    """
                    INSERT INTO elmer.agent_definitions
                        (name, display_name, description, system_prompt, model,
                         tools, triggers, output_channels, config,
                         enabled, max_concurrent, timeout_seconds)
                    VALUES ($1, $2, $3, $4, $5,
                            $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb,
                            $10, $11, $12)
                    """,
                    name,
                    data.get("display_name", ""),
                    data.get("description", ""),
                    data.get("system_prompt", ""),
                    data.get("model", "llama3.1:8b"),
                    json.dumps(tools),
                    json.dumps(raw_triggers),
                    json.dumps(data.get("output_channels", [])),
                    json.dumps(data.get("config", {})),
                    data.get("enabled", True),
                    data.get("max_concurrent", 1),
                    data.get("timeout_seconds", 120),
                )
                counts["registered"] += 1
                logger.info("Registered agent '%s' from %s", name, yaml_file.name)
            else:
                # Update if definition changed (prompt, description, or triggers).
                existing_triggers = _parse_json(existing.get("triggers")) or []
                if (
                    (existing["system_prompt"] or "") != (data.get("system_prompt") or "")
                    or (existing["description"] or "") != (data.get("description") or "")
                    or json.dumps(existing_triggers, sort_keys=True) != json.dumps(raw_triggers, sort_keys=True)
                ):
                    await db.execute(
                        """
                        UPDATE elmer.agent_definitions SET
                            display_name = $1, description = $2, system_prompt = $3,
                            model = $4, tools = $5::jsonb, triggers = $6::jsonb,
                            output_channels = $7::jsonb, config = $8::jsonb,
                            max_concurrent = $9, timeout_seconds = $10,
                            updated_at = now()
                        WHERE name = $11
                        """,
                        data.get("display_name", ""),
                        data.get("description", ""),
                        data.get("system_prompt", ""),
                        data.get("model", "llama3.1:8b"),
                        json.dumps(tools),
                        json.dumps(raw_triggers),
                        json.dumps(data.get("output_channels", [])),
                        json.dumps(data.get("config", {})),
                        data.get("max_concurrent", 1),
                        data.get("timeout_seconds", 120),
                        name,
                    )
                    counts["updated"] += 1
                    logger.info("Updated agent '%s' from %s", name, yaml_file.name)
                else:
                    counts["skipped"] += 1
        except Exception:
            logger.exception("Failed to load agent from %s", yaml_file)
            counts["errors"] += 1

    logger.info(
        "Agent definitions synced: %d registered, %d updated, %d skipped, %d errors",
        counts["registered"], counts["updated"], counts["skipped"], counts["errors"],
    )
    return counts


# ---------------------------------------------------------------------------
# Endpoints — Agent definitions
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AgentDefinitionResponse])
async def list_agents(enabled_only: bool = Query(False)):
    """List all agent definitions."""
    if enabled_only:
        rows = await db.fetch_all(
            "SELECT * FROM elmer.agent_definitions WHERE enabled = true ORDER BY name"
        )
    else:
        rows = await db.fetch_all(
            "SELECT * FROM elmer.agent_definitions ORDER BY name"
        )
    return [_row_to_response(r) for r in rows]


@router.get("/tools")
async def list_tools():
    """List all available built-in tools that agents can use."""
    from elmer_agents.tool_registry import get_registry

    registry = get_registry()
    tools = []
    for name in sorted(registry.list_tools()):
        cls = registry.get(name)
        if cls is not None:
            instance = cls()
            tools.append({
                "name": cls.name,
                "description": cls.description,
                "parameters": instance.parameters_schema(),
            })
    return tools


@router.get("/orchestrator/status")
async def get_orchestrator_status():
    """Return the orchestrator's current status."""
    from ..services.orchestrator_service import get_orchestrator

    orch = get_orchestrator()
    if orch is None:
        return {"running": False, "error": "Orchestrator not started"}
    return orch.get_status()


@router.post("/orchestrator/reload")
async def reload_orchestrator():
    """Reload all agent definitions and re-register triggers."""
    from ..services.orchestrator_service import get_orchestrator

    orch = get_orchestrator()
    if orch is None:
        raise HTTPException(status_code=503, detail="Orchestrator not running")
    result = await orch.reload()
    return {"reloaded": True, **result}


@router.get("/schedule")
async def list_scheduled_jobs():
    """List all scheduled agent jobs with next fire time."""
    from ..services.orchestrator_service import get_orchestrator

    orch = get_orchestrator()
    if orch is None:
        return []
    return orch._schedule_triggers.get_scheduled_jobs()


@router.get("/runs", response_model=list[AgentRunSummary])
async def list_all_runs(
    limit: int = Query(default=50, le=200),
    status: str | None = Query(default=None),
    trigger_type: str | None = Query(default=None),
):
    """List recent runs across all agents."""
    conditions = []
    params: list[Any] = []
    idx = 1

    if status:
        conditions.append(f"r.status = ${idx}")
        params.append(status)
        idx += 1
    if trigger_type:
        conditions.append(f"r.trigger_type = ${idx}")
        params.append(trigger_type)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = await db.fetch_all(
        f"""
        SELECT r.id, d.name AS agent_name, r.trigger_type, r.status,
               r.started_at, r.completed_at, r.duration_seconds
        FROM elmer.agent_runs r
        JOIN elmer.agent_definitions d ON d.id = r.agent_id
        {where}
        ORDER BY r.started_at DESC
        LIMIT ${idx}
        """,
        *params,
    )
    return [
        AgentRunSummary(
            id=r["id"],
            agent_name=r["agent_name"],
            trigger_type=r["trigger_type"],
            status=r["status"],
            started_at=str(r["started_at"]) if r.get("started_at") else None,
            completed_at=str(r["completed_at"]) if r.get("completed_at") else None,
            duration_seconds=r.get("duration_seconds"),
        )
        for r in rows
    ]


@router.get("/{name}", response_model=AgentDefinitionResponse)
async def get_agent(name: str):
    """Get a specific agent definition."""
    row = await db.fetch_one(
        "SELECT * FROM elmer.agent_definitions WHERE name = $1", name
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return _row_to_response(row)


@router.post("", response_model=AgentDefinitionResponse, status_code=201)
async def create_agent(request: AgentCreateRequest):
    """Create a new agent definition."""
    # Check for duplicate.
    existing = await db.fetch_one(
        "SELECT id FROM elmer.agent_definitions WHERE name = $1", request.name
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Agent '{request.name}' already exists")

    tools_json = json.dumps([t.model_dump() for t in request.tools])
    triggers_json = json.dumps([t.model_dump() for t in request.triggers])

    row = await db.fetch_one(
        """
        INSERT INTO elmer.agent_definitions
            (name, display_name, description, system_prompt, model,
             tools, triggers, output_channels, config,
             enabled, max_concurrent, timeout_seconds)
        VALUES ($1, $2, $3, $4, $5,
                $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb,
                $10, $11, $12)
        RETURNING *
        """,
        request.name,
        request.display_name,
        request.description,
        request.system_prompt,
        request.model,
        tools_json,
        triggers_json,
        json.dumps(request.output_channels),
        json.dumps(request.config),
        request.enabled,
        request.max_concurrent,
        request.timeout_seconds,
    )
    return _row_to_response(row)


@router.put("/{name}", response_model=AgentDefinitionResponse)
async def update_agent(name: str, request: AgentUpdateRequest):
    """Update an existing agent definition."""
    existing = await db.fetch_one(
        "SELECT id FROM elmer.agent_definitions WHERE name = $1", name
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    # Build dynamic SET clause.
    set_parts: list[str] = []
    values: list[Any] = []
    idx = 1

    simple_fields = {
        "display_name": request.display_name,
        "description": request.description,
        "system_prompt": request.system_prompt,
        "model": request.model,
        "enabled": request.enabled,
        "max_concurrent": request.max_concurrent,
        "timeout_seconds": request.timeout_seconds,
    }

    for col, val in simple_fields.items():
        if val is not None:
            set_parts.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

    # JSON fields.
    if request.tools is not None:
        set_parts.append(f"tools = ${idx}::jsonb")
        values.append(json.dumps([t.model_dump() for t in request.tools]))
        idx += 1
    if request.triggers is not None:
        set_parts.append(f"triggers = ${idx}::jsonb")
        values.append(json.dumps([t.model_dump() for t in request.triggers]))
        idx += 1
    if request.output_channels is not None:
        set_parts.append(f"output_channels = ${idx}::jsonb")
        values.append(json.dumps(request.output_channels))
        idx += 1
    if request.config is not None:
        set_parts.append(f"config = ${idx}::jsonb")
        values.append(json.dumps(request.config))
        idx += 1

    if not set_parts:
        row = await db.fetch_one(
            "SELECT * FROM elmer.agent_definitions WHERE name = $1", name
        )
        return _row_to_response(row)

    set_parts.append(f"updated_at = ${idx}")
    values.append(datetime.now(timezone.utc))
    idx += 1

    values.append(name)
    query = f"UPDATE elmer.agent_definitions SET {', '.join(set_parts)} WHERE name = ${idx} RETURNING *"
    row = await db.fetch_one(query, *values)

    # Reload triggers in the orchestrator.
    _reload_agent_triggers(name)

    return _row_to_response(row)


@router.delete("/{name}")
async def delete_agent(name: str):
    """Delete an agent definition."""
    result = await db.execute(
        "DELETE FROM elmer.agent_definitions WHERE name = $1", name
    )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    _reload_agent_triggers(name)
    return {"name": name, "deleted": True}


@router.post("/{name}/enable")
async def enable_agent(name: str):
    """Enable an agent."""
    result = await db.execute(
        "UPDATE elmer.agent_definitions SET enabled = true, updated_at = now() WHERE name = $1",
        name,
    )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    _reload_agent_triggers(name)
    return {"name": name, "enabled": True}


@router.post("/{name}/disable")
async def disable_agent(name: str):
    """Disable an agent."""
    result = await db.execute(
        "UPDATE elmer.agent_definitions SET enabled = false, updated_at = now() WHERE name = $1",
        name,
    )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    _reload_agent_triggers(name)
    return {"name": name, "enabled": False}


# ---------------------------------------------------------------------------
# Endpoints — Agent runs
# ---------------------------------------------------------------------------


@router.post("/{name}/run", response_model=AgentRunResponse)
async def trigger_agent_run(name: str, request: AgentRunRequest | None = None):
    """Manually trigger an agent run.

    Creates a run record and fires background execution. Returns
    immediately with status 'pending' — poll the run endpoint to
    track progress.
    """
    # Fetch full agent definition (executor needs all fields).
    row = await db.fetch_one(
        "SELECT * FROM elmer.agent_definitions WHERE name = $1", name
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    if not row["enabled"]:
        raise HTTPException(status_code=400, detail=f"Agent '{name}' is disabled")

    input_data = (request.input if request else {}) or {}

    run_row = await db.fetch_one(
        """
        INSERT INTO elmer.agent_runs
            (agent_id, trigger_type, trigger_data, input_data, status, started_at)
        VALUES ($1, 'api', '{}'::jsonb, $2::jsonb, 'pending', now())
        RETURNING *
        """,
        row["id"],
        json.dumps(input_data),
    )

    # Fire background execution.
    from ..services.agent_executor import execute_agent_run

    asyncio.create_task(
        execute_agent_run(dict(row), run_row["id"], input_data),
    )

    return AgentRunResponse(
        id=run_row["id"],
        agent_id=run_row["agent_id"],
        agent_name=name,
        trigger_type="api",
        trigger_data={},
        status=run_row["status"],
        input_data=input_data,
        output_data={},
        started_at=str(run_row["started_at"]) if run_row.get("started_at") else None,
        completed_at=None,
        duration_seconds=None,
        error=None,
    )


@router.get("/{name}/runs", response_model=list[AgentRunSummary])
async def list_agent_runs(
    name: str,
    limit: int = Query(default=20, le=100),
):
    """List recent runs for an agent."""
    # Verify agent exists.
    agent = await db.fetch_one(
        "SELECT id FROM elmer.agent_definitions WHERE name = $1", name
    )
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    rows = await db.fetch_all(
        """
        SELECT r.id, r.trigger_type, r.status, r.started_at,
               r.completed_at, r.duration_seconds
        FROM elmer.agent_runs r
        WHERE r.agent_id = $1
        ORDER BY r.started_at DESC
        LIMIT $2
        """,
        agent["id"],
        limit,
    )
    return [
        AgentRunSummary(
            id=r["id"],
            agent_name=name,
            trigger_type=r["trigger_type"],
            status=r["status"],
            started_at=str(r["started_at"]) if r.get("started_at") else None,
            completed_at=str(r["completed_at"]) if r.get("completed_at") else None,
            duration_seconds=r.get("duration_seconds"),
        )
        for r in rows
    ]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: int):
    """Get details for a specific run."""
    row = await db.fetch_one(
        """
        SELECT r.*, d.name AS agent_name
        FROM elmer.agent_runs r
        JOIN elmer.agent_definitions d ON d.id = r.agent_id
        WHERE r.id = $1
        """,
        run_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _row_to_run(row)

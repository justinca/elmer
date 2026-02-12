"""Agent registry — manages agent definitions in the database.

Provides CRUD operations for agent definitions and runs,
plus YAML loading for file-based agent configs.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .models import AgentDefinition, AgentRun, AgentTool, AgentTrigger

logger = logging.getLogger("elmer.agents.registry")


class AgentRegistry:
    """Manages agent definitions stored in ``elmer.agent_definitions``.

    Designed to be used by the Core API — takes a ``db`` module (the
    core's ``db.connection`` module) for database access.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # CRUD — Definitions
    # ------------------------------------------------------------------

    async def register(self, definition: AgentDefinition) -> int:
        """Store a new agent definition. Returns the new ID."""
        row = await self._db.fetch_one(
            """
            INSERT INTO elmer.agent_definitions
                (name, display_name, description, system_prompt, model,
                 tools, triggers, output_channels, config,
                 enabled, max_concurrent, timeout_seconds)
            VALUES ($1, $2, $3, $4, $5,
                    $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb,
                    $10, $11, $12)
            RETURNING id
            """,
            definition.name,
            definition.display_name,
            definition.description,
            definition.system_prompt,
            definition.model,
            json.dumps([t.model_dump() for t in definition.tools]),
            json.dumps([t.model_dump() for t in definition.triggers]),
            json.dumps(definition.output_channels),
            json.dumps(definition.config),
            definition.enabled,
            definition.max_concurrent,
            definition.timeout_seconds,
        )
        agent_id = row["id"]
        logger.info("Registered agent '%s' (id=%d)", definition.name, agent_id)
        return agent_id

    async def unregister(self, name: str) -> bool:
        """Delete an agent definition by name. Returns True if deleted."""
        result = await self._db.execute(
            "DELETE FROM elmer.agent_definitions WHERE name = $1", name
        )
        deleted = not result.endswith("0")
        if deleted:
            logger.info("Unregistered agent '%s'", name)
        return deleted

    async def get(self, name: str) -> AgentDefinition | None:
        """Get a single agent definition by name."""
        row = await self._db.fetch_one(
            "SELECT * FROM elmer.agent_definitions WHERE name = $1", name
        )
        if row is None:
            return None
        return self._row_to_definition(row)

    async def get_by_id(self, agent_id: int) -> AgentDefinition | None:
        """Get a single agent definition by ID."""
        row = await self._db.fetch_one(
            "SELECT * FROM elmer.agent_definitions WHERE id = $1", agent_id
        )
        if row is None:
            return None
        return self._row_to_definition(row)

    async def list_all(self, enabled_only: bool = False) -> list[AgentDefinition]:
        """List all agent definitions."""
        if enabled_only:
            rows = await self._db.fetch_all(
                "SELECT * FROM elmer.agent_definitions WHERE enabled = true ORDER BY name"
            )
        else:
            rows = await self._db.fetch_all(
                "SELECT * FROM elmer.agent_definitions ORDER BY name"
            )
        return [self._row_to_definition(r) for r in rows]

    async def update(self, name: str, updates: dict[str, Any]) -> AgentDefinition | None:
        """Update specific fields of an agent definition."""
        existing = await self.get(name)
        if existing is None:
            return None

        # Build SET clause from provided updates.
        set_parts: list[str] = []
        values: list[Any] = []
        idx = 1

        field_map = {
            "display_name": "display_name",
            "description": "description",
            "system_prompt": "system_prompt",
            "model": "model",
            "enabled": "enabled",
            "max_concurrent": "max_concurrent",
            "timeout_seconds": "timeout_seconds",
        }

        for py_field, db_col in field_map.items():
            if py_field in updates and updates[py_field] is not None:
                set_parts.append(f"{db_col} = ${idx}")
                values.append(updates[py_field])
                idx += 1

        # JSON fields need explicit cast.
        json_fields = {
            "tools": "tools",
            "triggers": "triggers",
            "output_channels": "output_channels",
            "config": "config",
        }
        for py_field, db_col in json_fields.items():
            if py_field in updates and updates[py_field] is not None:
                set_parts.append(f"{db_col} = ${idx}::jsonb")
                val = updates[py_field]
                if py_field == "tools":
                    val = [t.model_dump() if hasattr(t, "model_dump") else t for t in val]
                elif py_field == "triggers":
                    val = [t.model_dump() if hasattr(t, "model_dump") else t for t in val]
                values.append(json.dumps(val))
                idx += 1

        if not set_parts:
            return existing

        set_parts.append(f"updated_at = ${idx}")
        values.append(datetime.now(timezone.utc))
        idx += 1

        values.append(name)
        query = (
            f"UPDATE elmer.agent_definitions SET {', '.join(set_parts)} "
            f"WHERE name = ${idx}"
        )
        await self._db.execute(query, *values)
        logger.info("Updated agent '%s': %s", name, list(updates.keys()))
        return await self.get(name)

    async def enable(self, name: str) -> bool:
        """Enable an agent."""
        result = await self._db.execute(
            "UPDATE elmer.agent_definitions SET enabled = true, updated_at = now() "
            "WHERE name = $1",
            name,
        )
        return not result.endswith("0")

    async def disable(self, name: str) -> bool:
        """Disable an agent."""
        result = await self._db.execute(
            "UPDATE elmer.agent_definitions SET enabled = false, updated_at = now() "
            "WHERE name = $1",
            name,
        )
        return not result.endswith("0")

    # ------------------------------------------------------------------
    # CRUD — Runs
    # ------------------------------------------------------------------

    async def create_run(
        self,
        agent_id: int,
        trigger_type: str,
        trigger_data: dict | None = None,
        input_data: dict | None = None,
    ) -> int:
        """Create a new agent run record. Returns the run ID."""
        row = await self._db.fetch_one(
            """
            INSERT INTO elmer.agent_runs
                (agent_id, trigger_type, trigger_data, input_data, status, started_at)
            VALUES ($1, $2, $3::jsonb, $4::jsonb, 'running', now())
            RETURNING id
            """,
            agent_id,
            trigger_type,
            json.dumps(trigger_data or {}),
            json.dumps(input_data or {}),
        )
        return row["id"]

    async def complete_run(
        self,
        run_id: int,
        status: str,
        output_data: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Mark a run as completed/failed/timeout."""
        await self._db.execute(
            """
            UPDATE elmer.agent_runs SET
                status = $1,
                output_data = $2::jsonb,
                error = $3,
                completed_at = now(),
                duration_seconds = EXTRACT(EPOCH FROM (now() - started_at))
            WHERE id = $4
            """,
            status,
            json.dumps(output_data or {}),
            error,
            run_id,
        )

    async def get_run(self, run_id: int) -> AgentRun | None:
        """Get a specific run by ID."""
        row = await self._db.fetch_one(
            """
            SELECT r.*, d.name AS agent_name
            FROM elmer.agent_runs r
            JOIN elmer.agent_definitions d ON d.id = r.agent_id
            WHERE r.id = $1
            """,
            run_id,
        )
        if row is None:
            return None
        return self._row_to_run(row)

    async def list_runs(
        self,
        agent_name: str | None = None,
        limit: int = 20,
    ) -> list[AgentRun]:
        """List recent runs, optionally filtered by agent name."""
        if agent_name:
            rows = await self._db.fetch_all(
                """
                SELECT r.*, d.name AS agent_name
                FROM elmer.agent_runs r
                JOIN elmer.agent_definitions d ON d.id = r.agent_id
                WHERE d.name = $1
                ORDER BY r.started_at DESC
                LIMIT $2
                """,
                agent_name,
                limit,
            )
        else:
            rows = await self._db.fetch_all(
                """
                SELECT r.*, d.name AS agent_name
                FROM elmer.agent_runs r
                JOIN elmer.agent_definitions d ON d.id = r.agent_id
                ORDER BY r.started_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [self._row_to_run(r) for r in rows]

    # ------------------------------------------------------------------
    # YAML loading
    # ------------------------------------------------------------------

    def load_from_yaml(self, file_path: str | Path) -> AgentDefinition:
        """Load an agent definition from a YAML file."""
        path = Path(file_path)
        with path.open() as f:
            data = yaml.safe_load(f)

        # Normalize tools from YAML format.
        raw_tools = data.get("tools", [])
        tools = []
        for t in raw_tools:
            if isinstance(t, str):
                tools.append(AgentTool(name=t))
            elif isinstance(t, dict):
                tools.append(AgentTool(**t))

        # Normalize triggers.
        raw_triggers = data.get("triggers", [])
        triggers = []
        for t in raw_triggers:
            if isinstance(t, dict):
                triggers.append(AgentTrigger(**t))

        return AgentDefinition(
            name=data["name"],
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            model=data.get("model", "llama3.1:8b"),
            tools=tools,
            triggers=triggers,
            output_channels=data.get("output_channels", []),
            config=data.get("config", {}),
            enabled=data.get("enabled", True),
            max_concurrent=data.get("max_concurrent", 1),
            timeout_seconds=data.get("timeout_seconds", 120),
        )

    def load_directory(self, dir_path: str | Path) -> list[AgentDefinition]:
        """Load all YAML agent definitions from a directory."""
        path = Path(dir_path)
        if not path.is_dir():
            logger.warning("Agent definitions directory not found: %s", path)
            return []

        definitions: list[AgentDefinition] = []
        for yaml_file in sorted(path.glob("*.yaml")):
            try:
                defn = self.load_from_yaml(yaml_file)
                definitions.append(defn)
                logger.debug("Loaded agent definition: %s from %s", defn.name, yaml_file.name)
            except Exception:
                logger.exception("Failed to load agent definition from %s", yaml_file)

        logger.info("Loaded %d agent definition(s) from %s", len(definitions), path)
        return definitions

    async def sync_from_directory(self, dir_path: str | Path) -> dict[str, int]:
        """Load YAML definitions and upsert them into the database.

        Returns counts: {"registered": N, "updated": N, "skipped": N, "errors": N}
        """
        definitions = self.load_directory(dir_path)
        counts = {"registered": 0, "updated": 0, "skipped": 0, "errors": 0}

        for defn in definitions:
            try:
                existing = await self.get(defn.name)
                if existing is None:
                    await self.register(defn)
                    counts["registered"] += 1
                else:
                    # Update if the YAML has changed (compare key fields).
                    changed = (
                        existing.display_name != defn.display_name
                        or existing.description != defn.description
                        or existing.system_prompt != defn.system_prompt
                        or existing.model != defn.model
                        or existing.timeout_seconds != defn.timeout_seconds
                    )
                    if changed:
                        await self.update(
                            defn.name,
                            {
                                "display_name": defn.display_name,
                                "description": defn.description,
                                "system_prompt": defn.system_prompt,
                                "model": defn.model,
                                "tools": defn.tools,
                                "triggers": defn.triggers,
                                "output_channels": defn.output_channels,
                                "config": defn.config,
                                "max_concurrent": defn.max_concurrent,
                                "timeout_seconds": defn.timeout_seconds,
                            },
                        )
                        counts["updated"] += 1
                    else:
                        counts["skipped"] += 1
            except Exception:
                logger.exception("Failed to sync agent '%s'", defn.name)
                counts["errors"] += 1

        logger.info(
            "Agent sync: %d registered, %d updated, %d skipped, %d errors",
            counts["registered"],
            counts["updated"],
            counts["skipped"],
            counts["errors"],
        )
        return counts

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(val: Any) -> Any:
        """Parse a JSON value that may be a string or already-parsed."""
        if val is None:
            return None
        if isinstance(val, str):
            return json.loads(val)
        return val

    def _row_to_definition(self, row) -> AgentDefinition:
        """Convert a database row to an AgentDefinition."""
        raw_tools = self._parse_json(row.get("tools")) or []
        raw_triggers = self._parse_json(row.get("triggers")) or []
        raw_channels = self._parse_json(row.get("output_channels")) or []
        raw_config = self._parse_json(row.get("config")) or {}

        tools = [AgentTool(**t) if isinstance(t, dict) else AgentTool(name=str(t)) for t in raw_tools]
        triggers = [AgentTrigger(**t) for t in raw_triggers if isinstance(t, dict)]

        return AgentDefinition(
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
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _row_to_run(self, row) -> AgentRun:
        """Convert a database row to an AgentRun."""
        return AgentRun(
            id=row["id"],
            agent_id=row["agent_id"],
            agent_name=row.get("agent_name", ""),
            trigger_type=row.get("trigger_type", ""),
            trigger_data=self._parse_json(row.get("trigger_data")) or {},
            status=row.get("status", ""),
            input_data=self._parse_json(row.get("input_data")) or {},
            output_data=self._parse_json(row.get("output_data")) or {},
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            duration_seconds=row.get("duration_seconds"),
            error=row.get("error"),
        )

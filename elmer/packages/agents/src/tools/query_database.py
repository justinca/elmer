"""Query database tool — read-only SQL against the Elmer database."""

import asyncio
import logging
import re
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger("elmer.agents.tools.query_database")

_DANGEROUS_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
_MAX_ROWS = 100
_QUERY_TIMEOUT = 10.0


class QueryDatabaseTool(BaseTool):
    name = "query_database"
    description = "Run a read-only SQL SELECT query against the Elmer database."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query to execute",
                },
            },
            "required": ["query"],
        }

    async def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        query = (arguments.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, error="Empty query")

        # Safety: only SELECT allowed.
        if not query.upper().startswith("SELECT"):
            return ToolResult(success=False, error="Only SELECT queries are allowed")

        if _DANGEROUS_KEYWORDS.search(query):
            return ToolResult(success=False, error="Query contains forbidden keywords")

        # Validate tables against whitelist.
        allowed_tables = self.config.get("allowed_tables", [])
        if allowed_tables:
            found_table = False
            for table in allowed_tables:
                if table.lower() in query.lower():
                    found_table = True
                    break
            if not found_table:
                return ToolResult(
                    success=False,
                    error=f"Query must reference one of: {', '.join(allowed_tables)}",
                )

        # Enforce LIMIT.
        if "LIMIT" not in query.upper():
            query = query.rstrip(";") + f" LIMIT {_MAX_ROWS}"

        db = context["db"]
        try:
            rows = await asyncio.wait_for(
                db.fetch_all(query),
                timeout=_QUERY_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Query timed out (10s limit)")
        except Exception as exc:
            return ToolResult(success=False, error=f"Query failed: {exc}")

        # Convert asyncpg Records to plain dicts.
        results = [dict(r) for r in rows]

        # Stringify non-serialisable values.
        for row in results:
            for k, v in row.items():
                if not isinstance(v, (str, int, float, bool, type(None), list, dict)):
                    row[k] = str(v)

        return ToolResult(
            success=True,
            data={"rows": results, "row_count": len(results)},
        )

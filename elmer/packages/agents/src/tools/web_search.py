"""Web search tool — search the web via DuckDuckGo."""

import logging
from typing import Any

import httpx

from .base import BaseTool, ToolResult

logger = logging.getLogger("elmer.agents.tools.web_search")

_TIMEOUT = 30.0


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for current information, news, or facts not in the knowledge base."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results (1-10, default 5)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        query = arguments.get("query", "")
        if not query.strip():
            return ToolResult(success=False, error="Empty search query")

        max_results = min(int(arguments.get("max_results", 5)), 10)

        settings = context["settings"]
        host = settings.ELMER_CORE_HOST
        # 0.0.0.0 is a bind address, not valid for client connections.
        if host == "0.0.0.0":
            host = "127.0.0.1"
        core_url = f"http://{host}:{settings.ELMER_CORE_PORT}/search/web"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(core_url, json={
                    "query": query,
                    "max_results": max_results,
                })
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                # Truncate body fields for tool response context budget.
                for r in results:
                    if r.get("body") and len(r["body"]) > 1000:
                        r["body"] = r["body"][:1000] + "..."

                return ToolResult(
                    success=True,
                    data={
                        "results": results,
                        "query": query,
                        "result_count": len(results),
                    },
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, error="Web search timed out")
        except Exception as exc:
            return ToolResult(success=False, error=f"Web search failed: {exc}")

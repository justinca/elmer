"""Tool registry — maps tool names to implementations."""

import logging
from typing import Any

from .tools.base import BaseTool

logger = logging.getLogger("elmer.agents.tool_registry")


class ToolRegistry:
    """Registry of available agent tools."""

    def __init__(self) -> None:
        self._tools: dict[str, type[BaseTool]] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Auto-register all built-in tools."""
        from .tools.call_api import CallAPITool
        from .tools.publish_mqtt import PublishMQTTTool
        from .tools.query_database import QueryDatabaseTool
        from .tools.run_script import RunScriptTool
        from .tools.search_knowledge import SearchKnowledgeTool
        from .tools.send_telegram import SendTelegramTool

        for cls in [
            SearchKnowledgeTool,
            QueryDatabaseTool,
            SendTelegramTool,
            PublishMQTTTool,
            CallAPITool,
            RunScriptTool,
        ]:
            self.register(cls)

    def register(self, tool_cls: type[BaseTool]) -> None:
        """Register a tool class by its name."""
        self._tools[tool_cls.name] = tool_cls
        logger.debug("Registered tool: %s", tool_cls.name)

    def get(self, name: str) -> type[BaseTool] | None:
        """Look up a tool class by name."""
        return self._tools.get(name)

    def create_instance(self, name: str, config: dict[str, Any] | None = None) -> BaseTool | None:
        """Create a tool instance with the given config."""
        cls = self.get(name)
        if cls is None:
            return None
        return cls(config=config)

    def list_tools(self) -> list[str]:
        """Return names of all registered tools."""
        return list(self._tools.keys())


# Module-level singleton.
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Return the global ToolRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry

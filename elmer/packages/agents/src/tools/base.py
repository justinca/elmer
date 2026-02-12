"""Base tool interface for all Elmer agent tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result from a tool execution."""

    success: bool
    data: Any = None
    error: str | None = None


class BaseTool(ABC):
    """Abstract base class for agent tools.

    Subclasses must set ``name`` and ``description`` as class attributes
    and implement :meth:`parameters_schema` and :meth:`execute`.
    """

    name: str = ""
    description: str = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """Return JSON Schema for the tool's parameters.

        This is the ``function.parameters`` block sent to Ollama.
        """

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolResult:
        """Execute the tool with the given arguments.

        *context* provides runtime dependencies injected by the executor::

            {
                "db": db_module,
                "settings": settings_obj,
                "mqtt_publish": async_callable,
                "agent_name": str,
                "agent_config": dict,
            }
        """

    def to_ollama_tool(self) -> dict[str, Any]:
        """Build the Ollama tool-calling descriptor."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema(),
            },
        }

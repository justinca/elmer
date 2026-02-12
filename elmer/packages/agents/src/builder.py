"""Agent builder — constructs agents from YAML definitions."""

from pathlib import Path
from typing import Any

import yaml


def load_agent_definition(path: str | Path) -> dict[str, Any]:
    """Load an agent definition from a YAML file."""
    path = Path(path)
    with path.open() as f:
        return yaml.safe_load(f)


def build_agent(definition: dict[str, Any]) -> dict[str, Any]:
    """Build an agent instance from a definition.

    Returns a dict representing the agent configuration.
    Actual LLM integration to be wired in later.
    """
    return {
        "name": definition.get("name", "unnamed"),
        "description": definition.get("description", ""),
        "model": definition.get("model", "llama3"),
        "system_prompt": definition.get("system_prompt", ""),
        "tools": definition.get("tools", []),
    }

"""Agent orchestrator — manages agent routing and execution."""

from typing import Any

from .builder import build_agent, load_agent_definition


class Orchestrator:
    """Routes requests to the appropriate agent."""

    def __init__(self):
        self.agents: dict[str, dict[str, Any]] = {}

    def register_agent(self, definition_path: str):
        """Load and register an agent from a YAML definition."""
        definition = load_agent_definition(definition_path)
        agent = build_agent(definition)
        self.agents[agent["name"]] = agent

    def list_agents(self) -> list[str]:
        """Return names of all registered agents."""
        return list(self.agents.keys())

    async def route(self, agent_name: str, message: str) -> str:
        """Route a message to a specific agent.

        TODO: Wire to actual LLM backend via worker.
        """
        if agent_name not in self.agents:
            return f"Agent '{agent_name}' not found."

        return f"[{agent_name}] received: {message} (LLM not yet connected)"

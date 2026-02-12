"""HTTP client for the Elmer Core API."""

import os
from typing import Any

import httpx

CORE_BASE_URL = (
    f"http://{os.getenv('ELMER_CORE_HOST', 'localhost')}"
    f":{os.getenv('ELMER_CORE_PORT', '8100')}"
)

_TIMEOUT = 5.0


class ElmerAPI:
    """Synchronous client wrapping the Elmer Core REST API."""

    def __init__(self, base_url: str = CORE_BASE_URL):
        self.base_url = base_url

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        """Issue a GET request and return the JSON body, or None on error."""
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(f"{self.base_url}{path}", params=params)
                resp.raise_for_status()
                return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    def _post(self, path: str) -> dict | None:
        """Issue a POST request and return the JSON body, or None on error."""
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.post(f"{self.base_url}{path}")
                resp.raise_for_status()
                return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    # -- Health ---------------------------------------------------------------

    def get_health(self) -> dict[str, Any]:
        """GET /health -- Core service status."""
        data = self._get("/health")
        if data is None:
            return {
                "status": "unreachable",
                "service": "elmer-core",
                "version": "?",
                "uptime_seconds": 0,
            }
        return data

    def get_nodes(self) -> list[dict[str, Any]]:
        """GET /health/nodes -- all nodes with status."""
        data = self._get("/health/nodes")
        if data is None:
            return []
        return data.get("nodes", [])

    def get_node_detail(self, node_id: str) -> dict[str, Any] | None:
        """GET /health/nodes/{node_id} -- detailed status for one node."""
        return self._get(f"/health/nodes/{node_id}")

    def get_node_history(
        self, node_id: str, hours: int = 24
    ) -> list[dict[str, Any]]:
        """GET /health/nodes/{node_id}/history -- recent events."""
        data = self._get(
            f"/health/nodes/{node_id}/history", params={"hours": hours}
        )
        if data is None:
            return []
        return data.get("events", [])

    # -- Nodes ----------------------------------------------------------------

    def get_registered_nodes(self) -> list[dict[str, Any]]:
        """GET /nodes -- all registered nodes."""
        data = self._get("/nodes")
        if data is None:
            return []
        return data if isinstance(data, list) else data.get("nodes", [])

    def ping_node(self, node_id: str) -> dict[str, Any] | None:
        """POST /nodes/{node_id}/ping -- actively ping a node."""
        return self._post(f"/nodes/{node_id}/ping")

    # -- LLM (for services page) ----------------------------------------------

    def get_llm_models(self) -> list[dict[str, Any]]:
        """GET /llm/models -- available LLM models on worker."""
        data = self._get("/llm/models")
        if data is None:
            return []
        return data.get("models", [])

    # -- Events ---------------------------------------------------------------

    def get_events(self, hours: int = 24) -> list[dict[str, Any]]:
        """Aggregate events from all known nodes.

        There is no global /events endpoint yet, so we pull history
        from each node individually and merge.
        """
        nodes = self.get_nodes()
        all_events: list[dict[str, Any]] = []
        for node in nodes:
            node_id = node.get("node_id", "")
            if node_id:
                events = self.get_node_history(node_id, hours=hours)
                all_events.extend(events)
        all_events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return all_events

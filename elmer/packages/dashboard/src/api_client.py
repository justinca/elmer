"""HTTP client for the Elmer Core API."""

import os
from typing import Any

import httpx

CORE_BASE_URL = (
    f"http://{os.getenv('ELMER_CORE_HOST', 'localhost')}"
    f":{os.getenv('ELMER_CORE_PORT', '8100')}"
)

_TIMEOUT = 5.0
_LONG_TIMEOUT = 180.0  # For LLM / transcription calls.


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

    def _post(self, path: str, json: dict | None = None,
              timeout: float | None = None) -> dict | None:
        """Issue a POST request and return the JSON body, or None on error."""
        try:
            with httpx.Client(timeout=timeout or _TIMEOUT) as client:
                resp = client.post(f"{self.base_url}{path}", json=json)
                resp.raise_for_status()
                return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    def _delete(self, path: str) -> dict | None:
        """Issue a DELETE request and return the JSON body, or None on error."""
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.delete(f"{self.base_url}{path}")
                resp.raise_for_status()
                return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return None

    def _post_file(self, path: str, file_name: str, file_bytes: bytes,
                   mime: str, form_data: dict | None = None,
                   timeout: float | None = None) -> dict | None:
        """POST a file upload."""
        try:
            files = {"file": (file_name, file_bytes, mime)}
            with httpx.Client(timeout=timeout or _LONG_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}{path}",
                    files=files,
                    data=form_data,
                )
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
        """Aggregate events from all known nodes."""
        nodes = self.get_nodes()
        all_events: list[dict[str, Any]] = []
        for node in nodes:
            node_id = node.get("node_id", "")
            if node_id:
                events = self.get_node_history(node_id, hours=hours)
                all_events.extend(events)
        all_events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return all_events

    # -- Knowledge ------------------------------------------------------------

    def knowledge_search(
        self, query: str, limit: int = 5, threshold: float = 0.3,
        sources: list[str] | None = None,
    ) -> dict | None:
        """POST /knowledge/search -- semantic search."""
        payload: dict[str, Any] = {
            "query": query, "limit": limit, "threshold": threshold,
        }
        if sources:
            payload["sources"] = sources
        else:
            payload["sources"] = ["docs", "notes", "transcripts"]
        return self._post("/knowledge/search", json=payload, timeout=30.0)

    def knowledge_sources(self) -> list[dict[str, Any]]:
        """GET /knowledge/sources -- list sources with counts."""
        data = self._get("/knowledge/sources")
        return data if isinstance(data, list) else []

    def knowledge_delete_source(self, source: str) -> dict | None:
        """DELETE /knowledge/source/{source}."""
        return self._delete(f"/knowledge/source/{source}")

    def knowledge_ingest_directory(
        self, path: str, source: str,
        patterns: list[str] | None = None,
    ) -> dict | None:
        """POST /knowledge/ingest/directory."""
        return self._post("/knowledge/ingest/directory", json={
            "path": path, "source": source, "recursive": True,
            "patterns": patterns or ["*.md"],
        }, timeout=60.0)

    # -- Transcription --------------------------------------------------------

    def get_transcriptions(
        self, limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        """GET /transcription -- list transcriptions."""
        data = self._get("/transcription", params={
            "limit": limit, "offset": offset,
        })
        return data if isinstance(data, list) else []

    def get_transcription(self, tid: int) -> dict | None:
        """GET /transcription/{id} -- single transcription."""
        return self._get(f"/transcription/{tid}")

    def search_transcriptions(self, query: str, limit: int = 5) -> list[dict]:
        """GET /transcription/search?q=..."""
        data = self._get("/transcription/search", params={
            "q": query, "limit": limit,
        })
        return data if isinstance(data, list) else []

    def upload_transcription(
        self, filename: str, file_bytes: bytes, mime: str,
    ) -> dict | None:
        """POST /transcription/upload -- upload audio for transcription."""
        return self._post_file(
            "/transcription/upload", filename, file_bytes, mime,
        )

    # -- Notes ----------------------------------------------------------------

    def get_notes(self, limit: int = 50) -> list[dict[str, Any]]:
        """GET /notes -- list notes."""
        data = self._get("/notes", params={"limit": limit})
        return data if isinstance(data, list) else []

    def get_note(self, note_id: int) -> dict | None:
        """GET /notes/{id} -- single note."""
        return self._get(f"/notes/{note_id}")

    # -- Chat -----------------------------------------------------------------

    def chat(
        self, message: str,
        conversation_id: int | None = None,
        model: str = "llama3.1:8b",
    ) -> dict | None:
        """POST /chat -- send a RAG chat message."""
        payload: dict[str, Any] = {"message": message, "model": model}
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        return self._post("/chat", json=payload, timeout=_LONG_TIMEOUT)

    def list_conversations(
        self, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """GET /chat/conversations."""
        data = self._get("/chat/conversations", params={"limit": limit})
        return data if isinstance(data, list) else []

    def get_conversation(self, cid: int) -> dict | None:
        """GET /chat/conversation/{id}."""
        return self._get(f"/chat/conversation/{cid}")

    def delete_conversation(self, cid: int) -> dict | None:
        """DELETE /chat/conversation/{id}."""
        return self._delete(f"/chat/conversation/{cid}")

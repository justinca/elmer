"""HTTP client for the Elmer Core API."""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("elmer.dashboard.api")

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

    def _get(self, path: str, params: dict | None = None,
             timeout: float | None = None) -> dict | None:
        """Issue a GET request and return the JSON body, or None on error."""
        try:
            with httpx.Client(timeout=timeout or _TIMEOUT) as client:
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

    def _put(self, path: str, json: dict | None = None) -> dict | None:
        """Issue a PUT request and return the JSON body, or None on error."""
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.put(f"{self.base_url}{path}", json=json)
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
            logger.info("Uploading %s (%d bytes) to %s", file_name, len(file_bytes), path)
            files = {"file": (file_name, file_bytes, mime)}
            with httpx.Client(timeout=timeout or _LONG_TIMEOUT) as client:
                resp = client.post(
                    f"{self.base_url}{path}",
                    files=files,
                    data=form_data,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.error("Upload failed for %s: %s", path, exc)
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
        diarize: bool = False,
    ) -> dict | None:
        """POST /transcription/upload -- upload audio for transcription."""
        path = "/transcription/upload"
        if diarize:
            path += "?diarize=true"
        return self._post_file(path, filename, file_bytes, mime)

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

    # -- Agents ---------------------------------------------------------------

    def list_agents(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """GET /agents -- list all agent definitions."""
        params = {"enabled_only": str(enabled_only).lower()} if enabled_only else None
        data = self._get("/agents", params=params)
        return data if isinstance(data, list) else []

    def get_agent(self, name: str) -> dict | None:
        """GET /agents/{name} -- single agent definition."""
        return self._get(f"/agents/{name}")

    def create_agent(self, payload: dict) -> dict | None:
        """POST /agents -- create a new agent definition."""
        return self._post("/agents", json=payload)

    def update_agent(self, name: str, payload: dict) -> dict | None:
        """PUT /agents/{name} -- update an agent definition."""
        return self._put(f"/agents/{name}", json=payload)

    def delete_agent(self, name: str) -> dict | None:
        """DELETE /agents/{name}."""
        return self._delete(f"/agents/{name}")

    def enable_agent(self, name: str) -> dict | None:
        """POST /agents/{name}/enable."""
        return self._post(f"/agents/{name}/enable")

    def disable_agent(self, name: str) -> dict | None:
        """POST /agents/{name}/disable."""
        return self._post(f"/agents/{name}/disable")

    def trigger_agent_run(self, name: str, input_data: dict | None = None) -> dict | None:
        """POST /agents/{name}/run -- manually trigger an agent run."""
        payload = {"input": input_data} if input_data else {}
        return self._post(f"/agents/{name}/run", json=payload, timeout=_LONG_TIMEOUT)

    def list_agent_runs(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        """GET /agents/{name}/runs -- recent runs for an agent."""
        data = self._get(f"/agents/{name}/runs", params={"limit": limit})
        return data if isinstance(data, list) else []

    def list_all_runs(
        self, limit: int = 50, status: str | None = None,
        trigger_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /agents/runs -- recent runs across all agents."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if trigger_type:
            params["trigger_type"] = trigger_type
        data = self._get("/agents/runs", params=params)
        return data if isinstance(data, list) else []

    def get_agent_run(self, run_id: int) -> dict | None:
        """GET /agents/runs/{run_id} -- details for a specific run."""
        return self._get(f"/agents/runs/{run_id}")

    def list_tools(self) -> list[dict[str, Any]]:
        """GET /agents/tools -- available built-in tools."""
        data = self._get("/agents/tools")
        return data if isinstance(data, list) else []

    def get_orchestrator_status(self) -> dict | None:
        """GET /agents/orchestrator/status."""
        return self._get("/agents/orchestrator/status")

    def reload_orchestrator(self) -> dict | None:
        """POST /agents/orchestrator/reload."""
        return self._post("/agents/orchestrator/reload")

    def get_schedule(self) -> list[dict[str, Any]]:
        """GET /agents/schedule -- scheduled agent jobs."""
        data = self._get("/agents/schedule")
        return data if isinstance(data, list) else []

    # -- Propagation --------------------------------------------------------

    def get_propagation(self) -> dict[str, Any] | None:
        """GET /propagation -- current conditions summary."""
        return self._get("/propagation")

    def get_propagation_bands(self) -> dict[str, Any] | None:
        """GET /propagation/bands -- per-band conditions."""
        return self._get("/propagation/bands")

    def get_propagation_solar(self) -> dict[str, Any] | None:
        """GET /propagation/solar -- solar indices."""
        return self._get("/propagation/solar")

    def get_propagation_forecast(self) -> dict[str, Any] | None:
        """GET /propagation/forecast -- forecast data."""
        return self._get("/propagation/forecast")

    def get_propagation_history(self, hours: int = 24) -> list[dict[str, Any]]:
        """GET /propagation/history -- historical data."""
        data = self._get("/propagation/history", params={"hours": hours})
        return data if isinstance(data, list) else []

    def get_propagation_band(self, band: str) -> dict[str, Any] | None:
        """GET /propagation/band/{band} -- specific band detail."""
        return self._get(f"/propagation/band/{band}")

    # -- DX Cluster ---------------------------------------------------------

    def get_dx_spots(
        self, band: str | None = None, mode: str | None = None,
        entity: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """GET /dx/spots -- recent DX spots."""
        params: dict[str, Any] = {"limit": limit}
        if band:
            params["band"] = band
        if mode:
            params["mode"] = mode
        if entity:
            params["entity"] = entity
        data = self._get("/dx/spots", params=params)
        return data if isinstance(data, list) else []

    def get_dx_summary(self) -> dict[str, Any] | None:
        """GET /dx/spots/summary -- band activity summary."""
        return self._get("/dx/spots/summary")

    def get_dx_needs(self, entity: str | None = None) -> list[dict[str, Any]]:
        """GET /dx/needs -- needs list."""
        params = {"entity": entity} if entity else None
        data = self._get("/dx/needs", params=params)
        return data if isinstance(data, list) else []

    def add_dx_need(self, payload: dict) -> dict | None:
        """POST /dx/needs -- add to needs list."""
        return self._post("/dx/needs", json=payload)

    def delete_dx_need(self, need_id: int) -> dict | None:
        """DELETE /dx/needs/{id}."""
        return self._delete(f"/dx/needs/{need_id}")

    def get_dx_cluster_status(self) -> dict[str, Any] | None:
        """GET /dx/cluster/status."""
        return self._get("/dx/cluster/status")

    def lookup_entity(self, callsign: str) -> dict[str, Any] | None:
        """GET /dx/entities/{callsign}."""
        return self._get(f"/dx/entities/{callsign}")

    # -- Logbook (Log4OM) -----------------------------------------------------

    def get_log_status(self) -> dict[str, Any] | None:
        """GET /log/status -- Log4OM database status."""
        return self._get("/log/status")

    def get_log_qsos(
        self, limit: int = 50, offset: int = 0,
        call: str | None = None, band: str | None = None,
        mode: str | None = None, country: str | None = None,
        since: str | None = None, until: str | None = None,
    ) -> Any:
        """GET /log/qsos -- filtered QSO list."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if call:
            params["call"] = call
        if band:
            params["band"] = band
        if mode:
            params["mode"] = mode
        if country:
            params["country"] = country
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        return self._get("/log/qsos", params=params)

    def get_log_qso_count(self, **kwargs) -> dict[str, Any] | None:
        """GET /log/qsos/count."""
        params = {k: v for k, v in kwargs.items() if v is not None}
        return self._get("/log/qsos/count", params=params or None)

    def get_log_stats(self) -> dict[str, Any] | None:
        """GET /log/stats -- aggregate statistics."""
        return self._get("/log/stats")

    def get_log_dxcc(self) -> Any:
        """GET /log/dxcc -- DXCC entity summary."""
        return self._get("/log/dxcc")

    def search_log(self, q: str, limit: int = 50) -> Any:
        """GET /log/search?q=..."""
        return self._get("/log/search", params={"q": q, "limit": limit})

    def get_log_contests(self) -> Any:
        """GET /log/contests."""
        return self._get("/log/contests")

    def get_log_recent(self, limit: int = 20) -> Any:
        """GET /log/recent."""
        return self._get("/log/recent", params={"limit": limit})

    def sync_log(self) -> dict[str, Any] | None:
        """POST /log/sync -- sync log summaries to knowledge base."""
        return self._post("/log/sync", timeout=_LONG_TIMEOUT)

    def analyze_log(self, days: int = 30, focus: str | None = None) -> dict[str, Any] | None:
        """POST /log/analyze -- LLM analysis of log activity."""
        params: dict[str, Any] = {"days": days}
        if focus:
            params["focus"] = focus
        return self._post(f"/log/analyze?days={days}" + (f"&focus={focus}" if focus else ""),
                          timeout=_LONG_TIMEOUT)

    def check_log_needs(self) -> dict[str, Any] | None:
        """POST /log/needs-check -- cross-reference needs vs log."""
        return self._post("/log/needs-check", timeout=_LONG_TIMEOUT)

    # -- POTA ---------------------------------------------------------------

    def get_pota_nearby_parks(
        self, grid: str | None = None, radius: float = 50.0,
    ) -> list[dict[str, Any]]:
        """GET /pota/parks/nearby -- parks near a grid."""
        params: dict[str, Any] = {"radius": radius}
        if grid:
            params["grid"] = grid
        data = self._get("/pota/parks/nearby", params=params, timeout=30.0)
        return data if isinstance(data, list) else []

    def search_pota_parks(
        self, state: str | None = None, name: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /pota/parks/search -- search parks."""
        params: dict[str, Any] = {}
        if state:
            params["state"] = state
        if name:
            params["name"] = name
        data = self._get("/pota/parks/search", params=params, timeout=30.0)
        return data if isinstance(data, list) else []

    def get_pota_park(self, park_id: str) -> dict[str, Any] | None:
        """GET /pota/park/{id} -- park details."""
        return self._get(f"/pota/park/{park_id}", timeout=15.0)

    def get_pota_spots(self) -> list[dict[str, Any]]:
        """GET /pota/spots -- current activator spots."""
        data = self._get("/pota/spots", timeout=15.0)
        return data if isinstance(data, list) else []

    def get_pota_plan(self, park_id: str) -> dict[str, Any] | None:
        """GET /pota/plan/{park_id} -- activation plan."""
        return self._get(f"/pota/plan/{park_id}", timeout=30.0)

    def get_pota_band_plan(self, park_id: str) -> dict[str, Any] | None:
        """GET /pota/plan/{park_id}/bands -- band recommendations."""
        return self._get(f"/pota/plan/{park_id}/bands", timeout=15.0)

    # -- Radio Control / Band Scanner ----------------------------------------

    def get_radio_status(self) -> dict[str, Any] | None:
        """GET /radio/status -- CAT connection, freq, mode."""
        return self._get("/radio/status")

    def radio_connect(self) -> dict[str, Any] | None:
        """POST /radio/connect -- (re)connect the CAT serial port."""
        return self._post("/radio/connect")

    def set_radio_frequency(self, freq_hz: int) -> dict[str, Any] | None:
        """POST /radio/frequency."""
        return self._post("/radio/frequency", json={"frequency_hz": freq_hz})

    def set_radio_mode(self, mode: str) -> dict[str, Any] | None:
        """POST /radio/mode."""
        return self._post("/radio/mode", json={"mode": mode})

    def get_scanner_status(self) -> dict[str, Any] | None:
        """GET /radio/scanner/status."""
        return self._get("/radio/scanner/status")

    def scanner_start(self, dwell_seconds: int | None = None,
                      bands: list[str] | None = None) -> dict[str, Any] | None:
        """POST /radio/scanner/start."""
        payload: dict[str, Any] = {}
        if dwell_seconds:
            payload["dwell_seconds"] = dwell_seconds
        if bands:
            payload["bands"] = bands
        return self._post("/radio/scanner/start", json=payload or None)

    def scanner_stop(self) -> dict[str, Any] | None:
        """POST /radio/scanner/stop."""
        return self._post("/radio/scanner/stop")

    def scanner_pause(self) -> dict[str, Any] | None:
        """POST /radio/scanner/pause."""
        return self._post("/radio/scanner/pause")

    def scanner_resume(self) -> dict[str, Any] | None:
        """POST /radio/scanner/resume."""
        return self._post("/radio/scanner/resume")

    def scanner_next(self) -> dict[str, Any] | None:
        """POST /radio/scanner/next."""
        return self._post("/radio/scanner/next")

    def scanner_dwell(self, seconds: int) -> dict[str, Any] | None:
        """POST /radio/scanner/dwell."""
        return self._post("/radio/scanner/dwell", json={"seconds": seconds})

    # -- Contests -----------------------------------------------------------

    def get_upcoming_contests(self, days: int = 30) -> list[dict[str, Any]]:
        """GET /contest/upcoming -- upcoming contests."""
        data = self._get("/contest/upcoming", params={"days": days})
        return data if isinstance(data, list) else []

    def get_contest_info(self, name: str) -> dict[str, Any] | None:
        """GET /contest/{name} -- contest details."""
        return self._get(f"/contest/{name}")

    def get_contest_dashboard(self, name: str) -> dict[str, Any] | None:
        """GET /contest/{name}/dashboard -- live contest dashboard."""
        return self._get(f"/contest/{name}/dashboard", timeout=30.0)

    def get_contest_history(self) -> list[dict[str, Any]]:
        """GET /contest/history -- historical contest participation."""
        data = self._get("/contest/history")
        return data if isinstance(data, list) else []

    def recommend_band(
        self, current_band: str, contest: str | None = None,
    ) -> dict[str, Any] | None:
        """GET /contest/recommend-band -- band recommendation."""
        params: dict[str, Any] = {"current_band": current_band}
        if contest:
            params["contest"] = contest
        return self._get("/contest/recommend-band", params=params)

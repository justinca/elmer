"""Chat tool definitions for Ollama tool-calling.

Exposes AllStar, Log4OM, propagation, DX cluster, POTA, contests,
system health, and agent operations as tools the chat LLM can invoke.
"""

import json
import logging
from dataclasses import asdict
from typing import Any

logger = logging.getLogger("elmer.chat_tools")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _log_proxy(path: str, params: dict[str, Any] | None = None) -> Any:
    """Call a Worker /log4om/* endpoint."""
    import httpx
    from ..config import settings

    url = f"{settings.worker_base_url}/log4om{path}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _core_proxy(
    path: str,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
) -> Any:
    """Call a Core API endpoint internally (self-proxy)."""
    import httpx

    url = f"http://127.0.0.1:8100{path}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        if method == "POST":
            resp = await client.post(url, json=json_body or {}, params=params)
        elif method == "DELETE":
            resp = await client.delete(url, params=params)
        else:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Tool definitions (Ollama tool-calling format)
# ---------------------------------------------------------------------------

CHAT_TOOLS: list[dict[str, Any]] = [
    # ==================================================================
    # AllStar tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "allstar_status",
            "description": (
                "Get the current AllStar node status including online/offline state, "
                "uptime, TX stats, and list of connected nodes."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_connect",
            "description": "Connect to a remote AllStar node in transceive (two-way) mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "integer",
                        "description": "The remote AllStar node number to connect to.",
                    },
                },
                "required": ["node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_disconnect",
            "description": "Disconnect from a remote AllStar node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "integer",
                        "description": "The remote AllStar node number to disconnect from.",
                    },
                },
                "required": ["node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_disconnect_all",
            "description": (
                "Disconnect from ALL currently connected AllStar nodes. "
                "First fetches the connection list, then disconnects each one."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_monitor",
            "description": "Connect to a remote AllStar node in monitor (listen-only) mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "integer",
                        "description": "The remote AllStar node number to monitor.",
                    },
                },
                "required": ["node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_lookup",
            "description": "Look up an AllStar node in the directory to find its callsign, description, and location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {
                        "type": "integer",
                        "description": "The AllStar node number to look up.",
                    },
                },
                "required": ["node"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_find_active",
            "description": (
                "Get the list of currently active/keyed (transmitting) AllStar nodes "
                "across the network. Returns the list but does NOT connect."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_search_nodes",
            "description": (
                "Search the AllStar node directory by location, callsign, site name, "
                "or affiliation. Returns matching nodes with full details. Use a broad "
                "search term (e.g. 'estes park' not 'estes park pole hill') and then "
                "examine the results to find the best match."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (location, callsign, site name, or affiliation).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_connect_active",
            "description": (
                "Find a currently transmitting AllStar node and connect to it. "
                "Picks a random active node and connects in one step. "
                "Use this when the user says 'connect me to an active node' or "
                "'find an active node and connect'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allstar_search_and_connect",
            "description": (
                "Search for an AllStar node by location or description and connect "
                "to the best match. Use this when the user says something like "
                "'connect to the estes park pole hill node'. Pass the broad location "
                "as query and the specific detail as filter."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Broad search term (e.g. 'estes park').",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional specific detail to match in results (e.g. 'pole hill').",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # ==================================================================
    # Log / QSO tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "log_recent_qsos",
            "description": (
                "Get the most recent QSOs from the Log4OM logbook. "
                "Use this when the user asks about recent contacts, today's QSOs, "
                "or wants a summary of recent activity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent QSOs to return (default 20, max 100).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_search_qsos",
            "description": (
                "Search QSOs with filters. Use this to find contacts by callsign, "
                "band, mode, country, or date range. For 'today' use since=today's "
                "date in YYYY-MM-DD format."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "call": {
                        "type": "string",
                        "description": "Filter by callsign (partial match).",
                    },
                    "band": {
                        "type": "string",
                        "description": "Filter by band (e.g. '20m', '40m').",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Filter by mode (e.g. 'FT8', 'SSB', 'CW').",
                    },
                    "country": {
                        "type": "string",
                        "description": "Filter by DXCC country name.",
                    },
                    "since": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format.",
                    },
                    "until": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 50, max 500).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_stats",
            "description": (
                "Get aggregate log statistics: total QSOs, breakdown by band, "
                "mode, top DXCC entities worked. Use for overall log summaries."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_dxcc",
            "description": (
                "Get DXCC entity summary — which countries/entities have been worked "
                "and confirmed. Use when user asks about DXCC progress or countries worked."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # ==================================================================
    # Propagation tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "propagation_conditions",
            "description": (
                "Get current HF propagation conditions including solar flux index (SFI), "
                "sunspot number, A/K indices, X-ray flux, geomagnetic field status, "
                "and band-by-band conditions (day/night). Use for any question about "
                "propagation, solar conditions, or which bands are open."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propagation_band_detail",
            "description": (
                "Get detailed propagation info for a specific HF band including "
                "current condition, signal-to-noise ratio, and recent history. "
                "Band names: '80m-40m', '30m-20m', '17m-15m', '12m-10m'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "band": {
                        "type": "string",
                        "description": "Band name (e.g. '20m', '40m', '80m-40m', '12m-10m').",
                    },
                },
                "required": ["band"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propagation_forecast",
            "description": (
                "Get the HF propagation forecast including predicted conditions "
                "for the coming hours/days."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # ==================================================================
    # DX Cluster tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "dx_spots",
            "description": (
                "Get recent DX spots from the DX cluster. Can filter by band, mode, "
                "or DXCC entity. Use when user asks about DX spots, what's being "
                "spotted, or activity on a band."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "band": {
                        "type": "string",
                        "description": "Filter by band (e.g. '20m', '40m').",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Filter by mode (e.g. 'FT8', 'CW', 'SSB').",
                    },
                    "entity": {
                        "type": "string",
                        "description": "Filter by DXCC entity name.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max spots to return (default 30, max 200).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dx_spots_summary",
            "description": (
                "Get a quick summary of DX cluster activity: total spots in the "
                "last hour, breakdown by band and mode, and cluster connection status."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dx_lookup_entity",
            "description": (
                "Look up the DXCC entity for a callsign. Returns entity name, "
                "prefix, continent, CQ zone, and ITU zone."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "callsign": {
                        "type": "string",
                        "description": "The callsign to look up (e.g. 'JA1ABC', 'G4XYZ').",
                    },
                },
                "required": ["callsign"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dx_get_needs",
            "description": (
                "Get the DX needs list — entities/bands/modes still needed for "
                "DXCC awards. Use when user asks what they still need to work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "Optional: filter by specific DXCC entity name.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dx_add_need",
            "description": (
                "Add an entity/band/mode to the DX needs list. Use when the user "
                "says 'I need Japan on 20m CW' or 'add VK to my needs'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {
                        "type": "string",
                        "description": "DXCC entity name (e.g. 'Japan', 'Australia').",
                    },
                    "band": {
                        "type": "string",
                        "description": "Optional band (e.g. '20m').",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Optional mode (e.g. 'CW', 'FT8').",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 1-10, default 5. Higher = more important.",
                    },
                },
                "required": ["entity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dx_remove_need",
            "description": (
                "Remove an entry from the DX needs list by its ID. "
                "Get the ID from dx_get_needs first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "need_id": {
                        "type": "integer",
                        "description": "The need ID to remove.",
                    },
                },
                "required": ["need_id"],
            },
        },
    },
    # ==================================================================
    # POTA tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "pota_spots",
            "description": (
                "Get current Parks on the Air (POTA) activator spots — who is "
                "currently activating a park and on what frequency."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pota_search_parks",
            "description": (
                "Search for POTA parks by state or name. Use state codes like "
                "'US-CO' for Colorado, 'US-CA' for California."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "State code (e.g. 'US-CO', 'US-CA').",
                    },
                    "name": {
                        "type": "string",
                        "description": "Search by park name (substring match).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pota_nearby_parks",
            "description": (
                "Find POTA parks near a grid square. Defaults to home grid DN70 "
                "if no grid provided."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "grid": {
                        "type": "string",
                        "description": "4-character Maidenhead grid (e.g. 'DN70'). Defaults to home grid.",
                    },
                    "radius": {
                        "type": "number",
                        "description": "Search radius in miles (default 50, max 500).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pota_plan_activation",
            "description": (
                "Get a complete POTA activation plan for a park — recommended bands, "
                "frequencies, best times, and tips. Park references use format "
                "like 'US-1228'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": "Park reference (e.g. 'US-1228', 'US-0042').",
                    },
                },
                "required": ["reference"],
            },
        },
    },
    # ==================================================================
    # Contest tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "contest_upcoming",
            "description": (
                "Get upcoming ham radio contests. Shows contest name, dates, "
                "bands, modes, and exchange info."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "How many days ahead to look (default 30, max 365).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contest_recommend_band",
            "description": (
                "Get a band change recommendation during a contest based on "
                "current propagation and activity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "current_band": {
                        "type": "string",
                        "description": "Band you're currently on (e.g. '20m', '40m').",
                    },
                    "contest": {
                        "type": "string",
                        "description": "Optional contest name for context.",
                    },
                },
                "required": ["current_band"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contest_dashboard",
            "description": (
                "Get the live contest dashboard showing QSO rates, multipliers, "
                "and estimated score for an active contest."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contest": {
                        "type": "string",
                        "description": "Contest name/slug (e.g. 'cq-ww-ssb', 'arrl-sweepstakes').",
                    },
                },
                "required": ["contest"],
            },
        },
    },
    # ==================================================================
    # System health tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "system_status",
            "description": (
                "Get the overall system health status including Core uptime "
                "and status of all monitored nodes (ShackPi, WeatherPi, Worker, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_scheduler",
            "description": (
                "Get the status of all scheduled tasks/jobs and their next fire times."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # ==================================================================
    # Agent tools
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "agent_list",
            "description": (
                "List all configured AI agents with their names, descriptions, "
                "triggers, and enabled status."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_trigger",
            "description": (
                "Manually trigger an AI agent to run. Use when user says "
                "'run the daily briefing agent' or 'trigger the DX spotter'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Agent name (e.g. 'daily-briefing', 'dx-spotter').",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_recent_runs",
            "description": (
                "Get recent agent execution history showing which agents ran, "
                "when, their status (success/failed), and duration."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max runs to return (default 20, max 100).",
                    },
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a chat tool by name and return the result as a JSON string."""
    try:
        # -- AllStar tools -------------------------------------------------
        if name.startswith("allstar_"):
            return await _execute_allstar(name, arguments)

        # -- Log / QSO tools -----------------------------------------------
        if name.startswith("log_"):
            return await _execute_log(name, arguments)

        # -- Propagation tools ---------------------------------------------
        if name.startswith("propagation_"):
            return await _execute_propagation(name, arguments)

        # -- DX cluster tools ----------------------------------------------
        if name.startswith("dx_"):
            return await _execute_dx(name, arguments)

        # -- POTA tools ----------------------------------------------------
        if name.startswith("pota_"):
            return await _execute_pota(name, arguments)

        # -- Contest tools -------------------------------------------------
        if name.startswith("contest_"):
            return await _execute_contest(name, arguments)

        # -- System health tools -------------------------------------------
        if name.startswith("system_"):
            return await _execute_system(name, arguments)

        # -- Agent tools ---------------------------------------------------
        if name.startswith("agent_"):
            return await _execute_agent(name, arguments)

        return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as exc:
        logger.warning("Chat tool %s failed: %s", name, exc)
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# AllStar executor
# ---------------------------------------------------------------------------

async def _execute_allstar(name: str, arguments: dict[str, Any]) -> str:
    from .allstar import get_service

    svc = get_service()

    if name == "allstar_status":
        status = await svc.get_status()
        return json.dumps(asdict(status), default=str)

    elif name == "allstar_connect":
        node = int(arguments["node"])
        result = await svc.connect_node(node)
        return json.dumps(result)

    elif name == "allstar_disconnect":
        node = int(arguments["node"])
        result = await svc.disconnect_node(node)
        return json.dumps(result)

    elif name == "allstar_disconnect_all":
        connections = await svc.get_connections()
        if not connections:
            return json.dumps({"status": "ok", "message": "No nodes connected."})
        results = []
        for conn in connections:
            r = await svc.disconnect_node(conn.node)
            results.append({"node": conn.node, **r})
        return json.dumps({"status": "ok", "disconnected": results})

    elif name == "allstar_monitor":
        node = int(arguments["node"])
        result = await svc.monitor_node(node)
        return json.dumps(result)

    elif name == "allstar_lookup":
        node = int(arguments["node"])
        info = await svc.get_node_info(node)
        if info is None:
            return json.dumps({"error": f"Node {node} not found in directory."})
        return json.dumps(asdict(info))

    elif name == "allstar_find_active":
        nodes = await svc.get_keyed_nodes()
        return json.dumps({"keyed_nodes": nodes, "count": len(nodes)})

    elif name == "allstar_search_nodes":
        query = str(arguments.get("query", ""))
        results = await svc.search_nodes(query)
        return json.dumps({
            "results": [asdict(r) for r in results],
            "count": len(results),
            "query": query,
        })

    elif name == "allstar_connect_active":
        import random
        nodes = await svc.get_keyed_nodes()
        if not nodes:
            return json.dumps({"error": "No active/keyed nodes found."})
        chosen = random.choice(nodes)
        node_num = chosen["node"]
        result = await svc.connect_node(node_num)
        return json.dumps({
            "chosen_node": chosen,
            "connect_result": result,
        })

    elif name == "allstar_search_and_connect":
        query = str(arguments.get("query", ""))
        filt = str(arguments.get("filter", "")).lower()
        results = await svc.search_nodes(query)
        words = query.split()
        while not results and len(words) > 1:
            words = words[:-1]
            results = await svc.search_nodes(" ".join(words))
        if not results:
            return json.dumps({"error": f"No nodes found for '{query}'."})
        used_query = " ".join(words)
        leftover = query[len(used_query):].strip().lower()
        filter_term = filt or leftover
        best = results[0]
        if filter_term:
            for r in results:
                combined = f"{r.location} {r.site} {r.affiliation} {r.callsign}".lower()
                if filter_term in combined:
                    best = r
                    break
        result = await svc.connect_node(best.node)
        return json.dumps({
            "matched_node": asdict(best),
            "connect_result": result,
            "total_matches": len(results),
        })

    return json.dumps({"error": f"Unknown allstar tool: {name}"})


# ---------------------------------------------------------------------------
# Log executor
# ---------------------------------------------------------------------------

async def _execute_log(name: str, arguments: dict[str, Any]) -> str:
    if name == "log_recent_qsos":
        limit = min(int(arguments.get("limit", 20)), 100)
        data = await _log_proxy("/recent", {"limit": limit})
        return json.dumps(data, default=str)

    elif name == "log_search_qsos":
        params: dict[str, Any] = {}
        for key in ("call", "band", "mode", "country", "since", "until"):
            val = arguments.get(key)
            if val:
                params[key] = val
        params["limit"] = min(int(arguments.get("limit", 50)), 500)
        data = await _log_proxy("/qsos", params)
        return json.dumps(data, default=str)

    elif name == "log_stats":
        data = await _log_proxy("/stats")
        return json.dumps(data, default=str)

    elif name == "log_dxcc":
        data = await _log_proxy("/dxcc")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown log tool: {name}"})


# ---------------------------------------------------------------------------
# Propagation executor
# ---------------------------------------------------------------------------

async def _execute_propagation(name: str, arguments: dict[str, Any]) -> str:
    if name == "propagation_conditions":
        data = await _core_proxy("/propagation")
        return json.dumps(data, default=str)

    elif name == "propagation_band_detail":
        band = str(arguments.get("band", "20m"))
        data = await _core_proxy(f"/propagation/band/{band}")
        return json.dumps(data, default=str)

    elif name == "propagation_forecast":
        data = await _core_proxy("/propagation/forecast")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown propagation tool: {name}"})


# ---------------------------------------------------------------------------
# DX cluster executor
# ---------------------------------------------------------------------------

async def _execute_dx(name: str, arguments: dict[str, Any]) -> str:
    if name == "dx_spots":
        params: dict[str, Any] = {}
        for key in ("band", "mode", "entity"):
            val = arguments.get(key)
            if val:
                params[key] = val
        params["limit"] = min(int(arguments.get("limit", 30)), 200)
        data = await _core_proxy("/dx/spots", params=params)
        return json.dumps(data, default=str)

    elif name == "dx_spots_summary":
        data = await _core_proxy("/dx/spots/summary")
        return json.dumps(data, default=str)

    elif name == "dx_lookup_entity":
        callsign = str(arguments.get("callsign", "")).upper()
        data = await _core_proxy(f"/dx/entities/{callsign}")
        return json.dumps(data, default=str)

    elif name == "dx_get_needs":
        params = {}
        entity = arguments.get("entity")
        if entity:
            params["entity"] = entity
        data = await _core_proxy("/dx/needs", params=params)
        return json.dumps(data, default=str)

    elif name == "dx_add_need":
        body: dict[str, Any] = {"entity": str(arguments["entity"])}
        for key in ("band", "mode"):
            val = arguments.get(key)
            if val:
                body[key] = val
        if "priority" in arguments:
            body["priority"] = int(arguments["priority"])
        data = await _core_proxy("/dx/needs", method="POST", json_body=body)
        return json.dumps(data, default=str)

    elif name == "dx_remove_need":
        need_id = int(arguments["need_id"])
        data = await _core_proxy(f"/dx/needs/{need_id}", method="DELETE")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown dx tool: {name}"})


# ---------------------------------------------------------------------------
# POTA executor
# ---------------------------------------------------------------------------

async def _execute_pota(name: str, arguments: dict[str, Any]) -> str:
    if name == "pota_spots":
        data = await _core_proxy("/pota/spots")
        return json.dumps(data, default=str)

    elif name == "pota_search_parks":
        params: dict[str, Any] = {}
        if arguments.get("state"):
            params["state"] = arguments["state"]
        if arguments.get("name"):
            params["name"] = arguments["name"]
        data = await _core_proxy("/pota/parks/search", params=params)
        return json.dumps(data, default=str)

    elif name == "pota_nearby_parks":
        params: dict[str, Any] = {}
        if arguments.get("grid"):
            params["grid"] = arguments["grid"]
        if arguments.get("radius"):
            params["radius"] = str(arguments["radius"])
        data = await _core_proxy("/pota/parks/nearby", params=params)
        return json.dumps(data, default=str)

    elif name == "pota_plan_activation":
        ref = str(arguments.get("reference", ""))
        data = await _core_proxy(f"/pota/plan/{ref}")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown pota tool: {name}"})


# ---------------------------------------------------------------------------
# Contest executor
# ---------------------------------------------------------------------------

async def _execute_contest(name: str, arguments: dict[str, Any]) -> str:
    if name == "contest_upcoming":
        params: dict[str, Any] = {}
        if "days" in arguments:
            params["days"] = str(min(int(arguments["days"]), 365))
        data = await _core_proxy("/contest/upcoming", params=params)
        return json.dumps(data, default=str)

    elif name == "contest_recommend_band":
        params: dict[str, Any] = {
            "current_band": str(arguments["current_band"]),
        }
        if arguments.get("contest"):
            params["contest"] = arguments["contest"]
        data = await _core_proxy("/contest/recommend-band", params=params)
        return json.dumps(data, default=str)

    elif name == "contest_dashboard":
        contest = str(arguments.get("contest", ""))
        data = await _core_proxy(f"/contest/{contest}/dashboard")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown contest tool: {name}"})


# ---------------------------------------------------------------------------
# System health executor
# ---------------------------------------------------------------------------

async def _execute_system(name: str, arguments: dict[str, Any]) -> str:
    if name == "system_status":
        health = await _core_proxy("/health")
        nodes = await _core_proxy("/health/nodes")
        return json.dumps({
            "core": health,
            "nodes": nodes.get("nodes", []),
        }, default=str)

    elif name == "system_scheduler":
        data = await _core_proxy("/health/scheduler")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown system tool: {name}"})


# ---------------------------------------------------------------------------
# Agent executor
# ---------------------------------------------------------------------------

async def _execute_agent(name: str, arguments: dict[str, Any]) -> str:
    if name == "agent_list":
        data = await _core_proxy("/agents")
        # Trim to essential fields for the LLM
        summary = []
        for a in data:
            summary.append({
                "name": a.get("name"),
                "display_name": a.get("display_name"),
                "description": a.get("description"),
                "enabled": a.get("enabled"),
                "triggers": [
                    {"type": t.get("type"), "cron": t.get("cron"), "topic": t.get("topic")}
                    for t in a.get("triggers", [])
                ],
            })
        return json.dumps(summary, default=str)

    elif name == "agent_trigger":
        agent_name = str(arguments["name"])
        data = await _core_proxy(
            f"/agents/{agent_name}/run",
            method="POST",
            json_body={"input": {}},
        )
        return json.dumps(data, default=str)

    elif name == "agent_recent_runs":
        limit = min(int(arguments.get("limit", 20)), 100)
        data = await _core_proxy("/agents/runs", params={"limit": str(limit)})
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown agent tool: {name}"})

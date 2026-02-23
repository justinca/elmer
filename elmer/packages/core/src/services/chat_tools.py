"""Chat tool definitions for Ollama tool-calling.

Exposes 8 grouped dispatcher tools (allstar, log, propagation, dx, pota,
contest, system, agent) instead of 35 individual tools, reducing the
cognitive load on the small LLM.
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
# Tool definitions — 8 grouped dispatchers (Ollama tool-calling format)
# ---------------------------------------------------------------------------

CHAT_TOOLS: list[dict[str, Any]] = [
    # ==================================================================
    # AllStar
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "allstar",
            "description": (
                "Control and query the AllStar amateur radio linking system. "
                "Actions: status (get node status/connections), connect (connect to a node), "
                "disconnect (disconnect a node), disconnect_all (disconnect all nodes), "
                "monitor (listen-only to a node), lookup (directory lookup by node number), "
                "find_active (list currently transmitting nodes), search_nodes (search directory), "
                "connect_active (connect to a random active node), "
                "search_and_connect (search and connect to best match)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "status", "connect", "disconnect", "disconnect_all",
                            "monitor", "lookup", "find_active", "search_nodes",
                            "connect_active", "search_and_connect",
                        ],
                        "description": "The action to perform.",
                    },
                    "node": {
                        "type": "integer",
                        "description": "Node number (for connect, disconnect, monitor, lookup).",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search term (for search_nodes, search_and_connect).",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Specific detail to match in search results (for search_and_connect).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ==================================================================
    # Log / QSO
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "log",
            "description": (
                "Query the ham radio logbook (Log4OM). "
                "Actions: recent_qsos (get recent contacts), search_qsos (search with filters), "
                "stats (aggregate statistics), dxcc (DXCC entity progress)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["recent_qsos", "search_qsos", "stats", "dxcc"],
                        "description": "The action to perform.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return.",
                    },
                    "call": {
                        "type": "string",
                        "description": "Filter by callsign (for search_qsos).",
                    },
                    "band": {
                        "type": "string",
                        "description": "Filter by band e.g. '20m' (for search_qsos).",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Filter by mode e.g. 'FT8' (for search_qsos).",
                    },
                    "country": {
                        "type": "string",
                        "description": "Filter by DXCC country (for search_qsos).",
                    },
                    "since": {
                        "type": "string",
                        "description": "Start date YYYY-MM-DD (for search_qsos).",
                    },
                    "until": {
                        "type": "string",
                        "description": "End date YYYY-MM-DD (for search_qsos).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ==================================================================
    # Propagation
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "propagation",
            "description": (
                "Get HF radio propagation data. "
                "Actions: conditions (current solar/band conditions), "
                "band_detail (detailed info for one band), forecast (predicted conditions)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["conditions", "band_detail", "forecast"],
                        "description": "The action to perform.",
                    },
                    "band": {
                        "type": "string",
                        "description": "Band name for band_detail (e.g. '20m', '80m-40m').",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ==================================================================
    # DX Cluster
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "dx",
            "description": (
                "DX cluster spots and DXCC needs management. "
                "Actions: spots (recent DX spots, filterable), spots_summary (activity summary), "
                "lookup_entity (DXCC lookup by callsign), get_needs (view needs list), "
                "add_need (add entity/band/mode need), remove_need (remove a need by ID)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "spots", "spots_summary", "lookup_entity",
                            "get_needs", "add_need", "remove_need",
                        ],
                        "description": "The action to perform.",
                    },
                    "band": {
                        "type": "string",
                        "description": "Filter by band (for spots, add_need).",
                    },
                    "mode": {
                        "type": "string",
                        "description": "Filter by mode (for spots, add_need).",
                    },
                    "entity": {
                        "type": "string",
                        "description": "DXCC entity name (for lookup_entity, get_needs, add_need).",
                    },
                    "callsign": {
                        "type": "string",
                        "description": "Callsign to look up (for lookup_entity).",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 1-10 (for add_need, default 5).",
                    },
                    "need_id": {
                        "type": "integer",
                        "description": "Need ID to remove (for remove_need).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max spots to return (for spots).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ==================================================================
    # POTA
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "pota",
            "description": (
                "Parks on the Air (POTA) information. "
                "Actions: spots (current activator spots), search_parks (find parks by state/name), "
                "nearby_parks (parks near a grid square), plan_activation (activation plan for a park)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["spots", "search_parks", "nearby_parks", "plan_activation"],
                        "description": "The action to perform.",
                    },
                    "state": {
                        "type": "string",
                        "description": "State code e.g. 'US-CO' (for search_parks).",
                    },
                    "name": {
                        "type": "string",
                        "description": "Park name search (for search_parks).",
                    },
                    "grid": {
                        "type": "string",
                        "description": "Grid square e.g. 'DN70' (for nearby_parks, default home grid).",
                    },
                    "radius": {
                        "type": "number",
                        "description": "Search radius in miles (for nearby_parks, default 50).",
                    },
                    "reference": {
                        "type": "string",
                        "description": "Park reference e.g. 'US-1228' (for plan_activation).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ==================================================================
    # Contests
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "contest",
            "description": (
                "Ham radio contest information. "
                "Actions: upcoming (list upcoming contests), "
                "recommend_band (band change recommendation during contest), "
                "dashboard (live contest scoring dashboard)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["upcoming", "recommend_band", "dashboard"],
                        "description": "The action to perform.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Days ahead to look (for upcoming, default 30).",
                    },
                    "current_band": {
                        "type": "string",
                        "description": "Current band (for recommend_band).",
                    },
                    "contest": {
                        "type": "string",
                        "description": "Contest name/slug (for recommend_band, dashboard).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ==================================================================
    # System Health
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "system",
            "description": (
                "System health and monitoring. "
                "Actions: status (overall health + monitored nodes), "
                "scheduler (scheduled jobs and next fire times)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "scheduler"],
                        "description": "The action to perform.",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ==================================================================
    # Agents
    # ==================================================================
    {
        "type": "function",
        "function": {
            "name": "agent",
            "description": (
                "Manage AI agents. "
                "Actions: list (all agents with triggers/status), "
                "trigger (manually run an agent), "
                "recent_runs (execution history)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "trigger", "recent_runs"],
                        "description": "The action to perform.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Agent name (for trigger, e.g. 'daily-briefing').",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max runs to return (for recent_runs, default 20).",
                    },
                },
                "required": ["action"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _normalize_call(name: str, arguments: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Normalize old-format 'allstar_status' calls to grouped format.

    Returns (group, action, arguments).
    """
    # Already in grouped format — action is in arguments
    if name in ("allstar", "log", "propagation", "dx", "pota", "contest", "system", "agent"):
        action = str(arguments.get("action", ""))
        return name, action, arguments

    # Backward-compat: old "prefix_action" format
    for prefix in ("allstar", "propagation", "contest", "system", "agent", "pota", "log", "dx"):
        if name.startswith(prefix + "_"):
            action = name[len(prefix) + 1:]
            arguments.setdefault("action", action)
            return prefix, action, arguments

    return name, "", arguments


async def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a chat tool by name and return the result as a JSON string."""
    try:
        group, action, arguments = _normalize_call(name, arguments)

        if group == "allstar":
            return await _execute_allstar(action, arguments)
        if group == "log":
            return await _execute_log(action, arguments)
        if group == "propagation":
            return await _execute_propagation(action, arguments)
        if group == "dx":
            return await _execute_dx(action, arguments)
        if group == "pota":
            return await _execute_pota(action, arguments)
        if group == "contest":
            return await _execute_contest(action, arguments)
        if group == "system":
            return await _execute_system(action, arguments)
        if group == "agent":
            return await _execute_agent(action, arguments)

        return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as exc:
        logger.warning("Chat tool %s failed: %s", name, exc)
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# AllStar executor
# ---------------------------------------------------------------------------

async def _execute_allstar(action: str, arguments: dict[str, Any]) -> str:
    from .allstar import get_service

    svc = get_service()

    if action == "status":
        status = await svc.get_status()
        return json.dumps(asdict(status), default=str)

    if action == "connect":
        node = int(arguments["node"])
        result = await svc.connect_node(node)
        return json.dumps(result)

    if action == "disconnect":
        node = int(arguments["node"])
        result = await svc.disconnect_node(node)
        return json.dumps(result)

    if action == "disconnect_all":
        connections = await svc.get_connections()
        if not connections:
            return json.dumps({"status": "ok", "message": "No nodes connected."})
        results = []
        for conn in connections:
            r = await svc.disconnect_node(conn.node)
            results.append({"node": conn.node, **r})
        return json.dumps({"status": "ok", "disconnected": results})

    if action == "monitor":
        node = int(arguments["node"])
        result = await svc.monitor_node(node)
        return json.dumps(result)

    if action == "lookup":
        node = int(arguments["node"])
        info = await svc.get_node_info(node)
        if info is None:
            return json.dumps({"error": f"Node {node} not found in directory."})
        return json.dumps(asdict(info))

    if action == "find_active":
        nodes = await svc.get_keyed_nodes()
        return json.dumps({"keyed_nodes": nodes, "count": len(nodes)})

    if action == "search_nodes":
        query = str(arguments.get("query", ""))
        results = await svc.search_nodes(query)
        return json.dumps({
            "results": [asdict(r) for r in results],
            "count": len(results),
            "query": query,
        })

    if action == "connect_active":
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

    if action == "search_and_connect":
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

    return json.dumps({"error": f"Unknown allstar action: {action}"})


# ---------------------------------------------------------------------------
# Log executor
# ---------------------------------------------------------------------------

async def _execute_log(action: str, arguments: dict[str, Any]) -> str:
    if action == "recent_qsos":
        limit = min(int(arguments.get("limit", 20)), 100)
        data = await _log_proxy("/recent", {"limit": limit})
        return json.dumps(data, default=str)

    if action == "search_qsos":
        params: dict[str, Any] = {}
        for key in ("call", "band", "mode", "country", "since", "until"):
            val = arguments.get(key)
            if val:
                params[key] = val
        params["limit"] = min(int(arguments.get("limit", 50)), 500)
        data = await _log_proxy("/qsos", params)
        return json.dumps(data, default=str)

    if action == "stats":
        data = await _log_proxy("/stats")
        return json.dumps(data, default=str)

    if action == "dxcc":
        data = await _log_proxy("/dxcc")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown log action: {action}"})


# ---------------------------------------------------------------------------
# Propagation executor
# ---------------------------------------------------------------------------

async def _execute_propagation(action: str, arguments: dict[str, Any]) -> str:
    if action == "conditions":
        data = await _core_proxy("/propagation")
        return json.dumps(data, default=str)

    if action == "band_detail":
        band = str(arguments.get("band", "20m"))
        data = await _core_proxy(f"/propagation/band/{band}")
        return json.dumps(data, default=str)

    if action == "forecast":
        data = await _core_proxy("/propagation/forecast")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown propagation action: {action}"})


# ---------------------------------------------------------------------------
# DX cluster executor
# ---------------------------------------------------------------------------

async def _execute_dx(action: str, arguments: dict[str, Any]) -> str:
    if action == "spots":
        params: dict[str, Any] = {}
        for key in ("band", "mode", "entity"):
            val = arguments.get(key)
            if val:
                params[key] = val
        params["limit"] = min(int(arguments.get("limit", 30)), 200)
        data = await _core_proxy("/dx/spots", params=params)
        return json.dumps(data, default=str)

    if action == "spots_summary":
        data = await _core_proxy("/dx/spots/summary")
        return json.dumps(data, default=str)

    if action == "lookup_entity":
        callsign = str(arguments.get("callsign", "")).upper()
        data = await _core_proxy(f"/dx/entities/{callsign}")
        return json.dumps(data, default=str)

    if action == "get_needs":
        params = {}
        entity = arguments.get("entity")
        if entity:
            params["entity"] = entity
        data = await _core_proxy("/dx/needs", params=params)
        return json.dumps(data, default=str)

    if action == "add_need":
        body: dict[str, Any] = {"entity": str(arguments["entity"])}
        for key in ("band", "mode"):
            val = arguments.get(key)
            if val:
                body[key] = val
        if "priority" in arguments:
            body["priority"] = int(arguments["priority"])
        data = await _core_proxy("/dx/needs", method="POST", json_body=body)
        return json.dumps(data, default=str)

    if action == "remove_need":
        need_id = int(arguments["need_id"])
        data = await _core_proxy(f"/dx/needs/{need_id}", method="DELETE")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown dx action: {action}"})


# ---------------------------------------------------------------------------
# POTA executor
# ---------------------------------------------------------------------------

async def _execute_pota(action: str, arguments: dict[str, Any]) -> str:
    if action == "spots":
        data = await _core_proxy("/pota/spots")
        return json.dumps(data, default=str)

    if action == "search_parks":
        params: dict[str, Any] = {}
        if arguments.get("state"):
            params["state"] = arguments["state"]
        if arguments.get("name"):
            params["name"] = arguments["name"]
        data = await _core_proxy("/pota/parks/search", params=params)
        return json.dumps(data, default=str)

    if action == "nearby_parks":
        params: dict[str, Any] = {}
        if arguments.get("grid"):
            params["grid"] = arguments["grid"]
        if arguments.get("radius"):
            params["radius"] = str(arguments["radius"])
        data = await _core_proxy("/pota/parks/nearby", params=params)
        return json.dumps(data, default=str)

    if action == "plan_activation":
        ref = str(arguments.get("reference", ""))
        data = await _core_proxy(f"/pota/plan/{ref}")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown pota action: {action}"})


# ---------------------------------------------------------------------------
# Contest executor
# ---------------------------------------------------------------------------

async def _execute_contest(action: str, arguments: dict[str, Any]) -> str:
    if action == "upcoming":
        params: dict[str, Any] = {}
        if "days" in arguments:
            params["days"] = str(min(int(arguments["days"]), 365))
        data = await _core_proxy("/contest/upcoming", params=params)
        return json.dumps(data, default=str)

    if action == "recommend_band":
        params: dict[str, Any] = {
            "current_band": str(arguments["current_band"]),
        }
        if arguments.get("contest"):
            params["contest"] = arguments["contest"]
        data = await _core_proxy("/contest/recommend-band", params=params)
        return json.dumps(data, default=str)

    if action == "dashboard":
        contest = str(arguments.get("contest", ""))
        data = await _core_proxy(f"/contest/{contest}/dashboard")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown contest action: {action}"})


# ---------------------------------------------------------------------------
# System health executor
# ---------------------------------------------------------------------------

async def _execute_system(action: str, arguments: dict[str, Any]) -> str:
    if action == "status":
        health = await _core_proxy("/health")
        nodes = await _core_proxy("/health/nodes")
        return json.dumps({
            "core": health,
            "nodes": nodes.get("nodes", []),
        }, default=str)

    if action == "scheduler":
        data = await _core_proxy("/health/scheduler")
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown system action: {action}"})


# ---------------------------------------------------------------------------
# Agent executor
# ---------------------------------------------------------------------------

async def _execute_agent(action: str, arguments: dict[str, Any]) -> str:
    if action == "list":
        data = await _core_proxy("/agents")
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

    if action == "trigger":
        agent_name = str(arguments["name"])
        data = await _core_proxy(
            f"/agents/{agent_name}/run",
            method="POST",
            json_body={"input": {}},
        )
        return json.dumps(data, default=str)

    if action == "recent_runs":
        limit = min(int(arguments.get("limit", 20)), 100)
        data = await _core_proxy("/agents/runs", params={"limit": str(limit)})
        return json.dumps(data, default=str)

    return json.dumps({"error": f"Unknown agent action: {action}"})

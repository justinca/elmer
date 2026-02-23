"""Chat tool definitions for Ollama tool-calling.

Exposes AllStar operations as tools the chat LLM can invoke.
"""

import json
import logging
from dataclasses import asdict
from typing import Any

logger = logging.getLogger("elmer.chat_tools")

# ---------------------------------------------------------------------------
# Tool definitions (Ollama tool-calling format)
# ---------------------------------------------------------------------------

CHAT_TOOLS: list[dict[str, Any]] = [
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
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a chat tool by name and return the result as a JSON string."""
    from .allstar import get_service

    svc = get_service()

    try:
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
            # Try full query first; if no results, try dropping words
            # from the end (e.g. "estes park pole hill" -> "estes park pole" -> "estes park")
            results = await svc.search_nodes(query)
            words = query.split()
            while not results and len(words) > 1:
                words = words[:-1]
                results = await svc.search_nodes(" ".join(words))
            if not results:
                return json.dumps({"error": f"No nodes found for '{query}'."})
            # Use remaining original words as filter terms
            used_query = " ".join(words)
            leftover = query[len(used_query):].strip().lower()
            filter_term = filt or leftover
            # Pick best match based on filter
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

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as exc:
        logger.warning("Chat tool %s failed: %s", name, exc)
        return json.dumps({"error": str(exc)})

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
                "across the network. Use this to find a live node to connect to."
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

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as exc:
        logger.warning("Chat tool %s failed: %s", name, exc)
        return json.dumps({"error": str(exc)})

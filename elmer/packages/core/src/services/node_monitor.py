"""Node health monitor for Elmer Core.

Maintains a registry of all nodes in the Elmer network, detects missing
heartbeats, publishes alerts, and stores status history in ``elmer.events``.

Designed to be instantiated once by the Core lifespan and wired into
the existing MQTT heartbeat callback.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..db import connection as db

logger = logging.getLogger("elmer.node_monitor")


class NodeStatus:
    """In-memory representation of a registered node."""

    __slots__ = (
        "name", "node_type", "expected_interval", "status",
        "last_seen", "metadata",
    )

    def __init__(
        self,
        name: str,
        node_type: str,
        expected_interval: float = 30.0,
    ) -> None:
        self.name = name
        self.node_type = node_type
        self.expected_interval = expected_interval
        self.status: str = "unknown"
        self.last_seen: datetime | None = None
        self.metadata: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "node_type": self.node_type,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "expected_interval": self.expected_interval,
            "metadata": self.metadata,
        }


class NodeMonitor:
    """Central node health monitor.

    Parameters
    ----------
    mqtt_publish
        Async callable ``(topic, payload)`` to publish MQTT messages.
        Typically ``mqtt_service.publish``.
    missed_threshold
        Number of missed heartbeat intervals before a node is marked
        unreachable.
    """

    def __init__(
        self,
        mqtt_publish: Any = None,
        missed_threshold: int = 3,
    ) -> None:
        self._nodes: dict[str, NodeStatus] = {}
        self._mqtt_publish = mqtt_publish
        self._missed_threshold = missed_threshold

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_node(
        self,
        name: str,
        node_type: str,
        expected_interval: float = 30.0,
    ) -> NodeStatus:
        """Register (or update) a node in the monitor."""
        if name in self._nodes:
            node = self._nodes[name]
            node.node_type = node_type
            node.expected_interval = expected_interval
        else:
            node = NodeStatus(name, node_type, expected_interval)
            self._nodes[name] = node
            logger.info(
                "Registered node '%s' (type=%s, interval=%.0fs)",
                name, node_type, expected_interval,
            )
        return node

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_node_status(self, name: str) -> NodeStatus | None:
        """Return the status for a single node, or ``None`` if not found."""
        return self._nodes.get(name)

    def get_all_nodes(self) -> list[NodeStatus]:
        """Return status for all registered nodes."""
        return list(self._nodes.values())

    async def get_node_history(
        self,
        name: str,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Fetch recent events for *name* from ``elmer.events``.

        Returns up to 500 rows within the last *hours* hours.
        """
        pool = db.get_pool()
        if pool is None:
            return []

        try:
            rows = await db.fetch_all(
                """
                SELECT id, timestamp, source, event_type, data, created_at
                FROM elmer.events
                WHERE source = $1
                  AND timestamp > now() - make_interval(hours => $2)
                ORDER BY timestamp DESC
                LIMIT 500
                """,
                name,
                hours,
            )
            return [
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"].isoformat(),
                    "source": r["source"],
                    "event_type": r["event_type"],
                    "data": json.loads(r["data"]) if isinstance(r["data"], str) else r["data"],
                }
                for r in rows
            ]
        except Exception:
            logger.debug("Failed to fetch history for %s", name, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Heartbeat processing (called from MQTT callback)
    # ------------------------------------------------------------------

    async def on_heartbeat(self, node_name: str, payload: dict) -> None:
        """Process an incoming heartbeat and update the node registry."""
        now = datetime.now(timezone.utc)

        if node_name not in self._nodes:
            self.register_node(
                node_name,
                node_type=payload.get("node_type", "unknown"),
            )

        node = self._nodes[node_name]
        node.status = payload.get("status", "online")
        node.last_seen = now
        node.metadata = payload.get("details", {})

        # Persist event
        await self._persist_event(node_name, "heartbeat", payload)

    # ------------------------------------------------------------------
    # Staleness check (called periodically)
    # ------------------------------------------------------------------

    async def check_stale_nodes(self) -> None:
        """Mark nodes as unreachable if heartbeats have stopped."""
        now = datetime.now(timezone.utc)

        for name, node in self._nodes.items():
            if name == "core":
                continue
            if node.last_seen is None:
                continue

            timeout = node.expected_interval * self._missed_threshold
            delta = (now - node.last_seen).total_seconds()

            if delta > timeout and node.status not in ("offline", "unreachable"):
                prev = node.status
                node.status = "unreachable"
                logger.warning(
                    "Node '%s' unreachable (no heartbeat for %ds, was %s)",
                    name, int(delta), prev,
                )

                alert = {"node": name, "last_seen": node.last_seen.isoformat(), "previous_status": prev}
                await self._persist_event("core", "node_unreachable", alert)

                if self._mqtt_publish is not None:
                    try:
                        await self._mqtt_publish(
                            f"elmer/events/core/node_unreachable",
                            {
                                "source": "core",
                                "event_type": "node_unreachable",
                                "data": alert,
                                "timestamp": now.isoformat(),
                            },
                        )
                    except Exception:
                        logger.debug("Failed to publish unreachable alert for %s", name)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _persist_event(self, source: str, event_type: str, data: Any) -> None:
        """Insert a row into ``elmer.events`` if the DB is available."""
        pool = db.get_pool()
        if pool is None:
            return
        try:
            await db.execute(
                "INSERT INTO elmer.events (source, event_type, data) VALUES ($1, $2, $3)",
                source,
                event_type,
                json.dumps(data, default=str),
            )
        except Exception:
            logger.debug("Failed to persist event %s/%s", source, event_type, exc_info=True)

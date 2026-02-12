"""Auto-documentation engine for the Elmer network.

Discovers live system state (nodes, services, config) and generates
human-readable markdown files plus RAG-indexable rows in ``elmer.documents``.

Follows the NodeMonitor singleton pattern — instantiated once in the lifespan,
injected via ``set_documentor()``.
"""

import asyncio
import hashlib
import json
import logging
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from ..db import connection as db
from ..models.docs import DeviceInfo, ServiceInfo

logger = logging.getLogger("elmer.autodoc")

# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_documentor: Any = None


def get_documentor():
    """Return the SystemDocumentor instance (may be ``None`` before startup)."""
    return _documentor


def set_documentor(doc):
    """Set the module-level SystemDocumentor instance."""
    global _documentor
    _documentor = doc


# ---------------------------------------------------------------------------
# Static service registry
# ---------------------------------------------------------------------------

_KNOWN_SERVICES: list[dict[str, Any]] = [
    {
        "name": "Core API",
        "device": "nuc",
        "host_setting": "ELMER_CORE_HOST",
        "port_setting": "ELMER_CORE_PORT",
        "container": "elmer-core",
        "health_endpoint": "/health",
        "protocol": "http",
    },
    {
        "name": "Dashboard",
        "device": "nuc",
        "host_setting": "ELMER_CORE_HOST",
        "port": 8501,
        "container": "elmer-dashboard",
        "health_endpoint": "/",
        "protocol": "http",
    },
    {
        "name": "Worker API",
        "device": "worker",
        "host_setting": "ELMER_WORKER_HOST",
        "port_setting": "ELMER_WORKER_PORT",
        "container": "",
        "health_endpoint": "/health",
        "protocol": "http",
    },
    {
        "name": "PostgreSQL",
        "device": "nuc",
        "host_setting": "POSTGRES_HOST",
        "port_setting": "POSTGRES_PORT",
        "container": "elmer-postgres",
        "health_endpoint": "",
        "protocol": "tcp",
    },
    {
        "name": "MQTT",
        "device": "nuc",
        "host_setting": "MQTT_HOST",
        "port_setting": "MQTT_PORT",
        "container": "elmer-mqtt",
        "health_endpoint": "",
        "protocol": "tcp",
    },
    {
        "name": "Ollama",
        "device": "nuc",
        "host_setting": "OLLAMA_HOST",
        "port_setting": "OLLAMA_PORT",
        "container": "",
        "health_endpoint": "/api/tags",
        "protocol": "http",
    },
]


def _resolve_host_port(svc: dict) -> tuple[str, int]:
    """Resolve host/port from settings attributes or static values."""
    host = getattr(settings, svc.get("host_setting", ""), "") or svc.get("host", "")
    port = svc.get("port") or getattr(settings, svc.get("port_setting", ""), 0)
    return str(host), int(port)


# ---------------------------------------------------------------------------
# SystemDocumentor
# ---------------------------------------------------------------------------


class SystemDocumentor:
    """Core auto-documentation engine.

    Parameters
    ----------
    node_monitor
        The NodeMonitor instance for discovering live node state.
    docs_dir
        Directory for generated markdown files (relative to project root).
    """

    def __init__(self, node_monitor: Any, docs_dir: str = "docs/auto") -> None:
        self._node_monitor = node_monitor
        self._docs_dir = Path(docs_dir)
        self._last_generation: datetime | None = None
        self._last_snapshots: dict[str, str] = {}  # filename -> content hash

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_nodes(self) -> list[DeviceInfo]:
        """Merge NodeMonitor state with the legacy node_registry."""
        from .mqtt_service import node_registry

        devices: dict[str, DeviceInfo] = {}

        # Primary source: NodeMonitor
        if self._node_monitor is not None:
            for node in self._node_monitor.get_all_nodes():
                meta = node.metadata or {}
                reg = node_registry.get(node.name, {})
                devices[node.name] = DeviceInfo(
                    node_id=node.name,
                    name=meta.get("hostname", reg.get("name", node.name)),
                    node_type=node.node_type,
                    status=node.status,
                    host=reg.get("host", ""),
                    port=reg.get("port", 0),
                    platform=meta.get("platform", ""),
                    hostname=meta.get("hostname", ""),
                    cpu_percent=meta.get("cpu_percent"),
                    ram_total_gb=meta.get("ram_total_gb"),
                    ram_used_gb=meta.get("ram_used_gb"),
                    disk_total_gb=meta.get("disk_total_gb"),
                    disk_used_gb=meta.get("disk_used_gb"),
                    last_seen=node.last_seen,
                    metadata=meta,
                )

        # Fill in any registry-only entries not yet in NodeMonitor.
        for node_id, info in node_registry.items():
            if node_id not in devices:
                meta = info.get("metadata", {})
                devices[node_id] = DeviceInfo(
                    node_id=node_id,
                    name=info.get("name", node_id),
                    node_type=info.get("node_type", "unknown"),
                    status=info.get("status", "unknown"),
                    host=info.get("host", ""),
                    port=info.get("port", 0),
                    platform=meta.get("platform", ""),
                    hostname=meta.get("hostname", ""),
                    last_seen=info.get("last_seen"),
                    metadata=meta,
                )

        return list(devices.values())

    async def discover_services(self) -> list[ServiceInfo]:
        """Check known services for reachability."""
        results: list[ServiceInfo] = []

        for svc in _KNOWN_SERVICES:
            host, port = _resolve_host_port(svc)
            status = "unknown"

            if svc["protocol"] == "http" and svc.get("health_endpoint"):
                status = await self._check_http(host, port, svc["health_endpoint"])
            elif host and port:
                status = await self._check_tcp(host, port)

            results.append(
                ServiceInfo(
                    name=svc["name"],
                    device=svc.get("device", ""),
                    host=host,
                    port=port,
                    status=status,
                    container=svc.get("container", ""),
                    health_endpoint=svc.get("health_endpoint", ""),
                )
            )

        return results

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    @staticmethod
    async def _check_http(host: str, port: int, path: str) -> str:
        url = f"http://{host}:{port}{path}"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                return "online" if resp.status_code < 500 else "degraded"
        except Exception:
            return "offline"

    @staticmethod
    async def _check_tcp(host: str, port: int) -> str:
        try:
            loop = asyncio.get_event_loop()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            await loop.run_in_executor(None, sock.connect, (host, port))
            sock.close()
            return "online"
        except Exception:
            return "offline"

    # ------------------------------------------------------------------
    # Markdown generators
    # ------------------------------------------------------------------

    def _doc_header(self, title: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        prev = (
            self._last_generation.strftime("%Y-%m-%d %H:%M:%S UTC")
            if self._last_generation
            else "N/A"
        )
        return (
            f"# {title}\n\n"
            f"> Auto-generated: {now}  \n"
            f"> Previous generation: {prev}\n\n"
        )

    def generate_inventory(self, nodes: list[DeviceInfo]) -> str:
        """Generate device inventory markdown."""
        md = self._doc_header("Device Inventory")

        md += "| Node | Type | Status | Hostname | Platform | RAM (GB) | Disk (GB) | Last Seen |\n"
        md += "|------|------|--------|----------|----------|----------|-----------|----------|\n"

        for d in nodes:
            ram = f"{d.ram_used_gb:.1f}/{d.ram_total_gb:.1f}" if d.ram_total_gb else "—"
            disk = f"{d.disk_used_gb:.1f}/{d.disk_total_gb:.1f}" if d.disk_total_gb else "—"
            last = d.last_seen.strftime("%Y-%m-%d %H:%M") if d.last_seen else "never"
            md += (
                f"| {d.node_id} | {d.node_type} | {d.status} | "
                f"{d.hostname or '—'} | {d.platform or '—'} | {ram} | {disk} | {last} |\n"
            )

        return md

    def generate_services(self, services: list[ServiceInfo]) -> str:
        """Generate service catalog markdown."""
        md = self._doc_header("Service Catalog")

        md += "| Service | Device | Host:Port | Container | Status | Health Endpoint |\n"
        md += "|---------|--------|-----------|-----------|--------|-----------------|\n"

        for s in services:
            hp = f"{s.host}:{s.port}" if s.host else "—"
            container = s.container or "—"
            endpoint = s.health_endpoint or "—"
            md += f"| {s.name} | {s.device} | {hp} | {container} | {s.status} | {endpoint} |\n"

        return md

    def generate_network_map(
        self, nodes: list[DeviceInfo], services: list[ServiceInfo]
    ) -> str:
        """Generate network map markdown with port table and topology."""
        md = self._doc_header("Network Map")

        # Port assignments
        md += "## Port Assignments\n\n"
        md += "| Service | Port | Protocol |\n"
        md += "|---------|------|----------|\n"
        for s in services:
            proto = "TCP"
            for known in _KNOWN_SERVICES:
                if known["name"] == s.name:
                    proto = known.get("protocol", "tcp").upper()
                    break
            md += f"| {s.name} | {s.port} | {proto} |\n"

        # MQTT topology
        md += "\n## MQTT Topology\n\n"
        md += "| Topic Pattern | Publisher | Subscriber |\n"
        md += "|---------------|-----------|------------|\n"
        md += "| `elmer/+/heartbeat` | All nodes | Core API |\n"
        md += "| `elmer/+/status` | All nodes | Core API |\n"
        md += "| `elmer/events/#` | Core API | Core API, Dashboard |\n"
        md += "| `elmer/core/status` | Core API | All nodes |\n"

        # ASCII diagram
        md += "\n## Connection Diagram\n\n```\n"
        node_names = [n.node_id for n in nodes] or ["(no nodes)"]
        md += "                    ┌─────────────┐\n"
        md += "                    │  MQTT Broker │\n"
        md += "                    └──────┬───────┘\n"
        md += "                           │\n"
        md += "              ┌────────────┼────────────┐\n"
        md += "              │            │            │\n"
        md += "        ┌─────┴─────┐ ┌────┴────┐ ┌────┴────┐\n"

        labels = (node_names + ["", "", ""])[:3]
        md += f"        │ {labels[0]:^9s} │ │ {labels[1]:^7s} │ │ {labels[2]:^7s} │\n"
        md += "        └───────────┘ └─────────┘ └─────────┘\n"
        md += "```\n"

        return md

    def generate_config_summary(self) -> str:
        """Generate config summary with secret redaction."""
        md = self._doc_header("Configuration Summary")

        sensitive_keywords = {"password", "token", "secret", "key"}

        md += "## Settings\n\n"
        md += "| Setting | Value |\n"
        md += "|---------|-------|\n"

        for field_name in sorted(settings.model_fields):
            value = getattr(settings, field_name)
            # Redact sensitive values
            if any(kw in field_name.lower() for kw in sensitive_keywords) and value:
                display = "***REDACTED***"
            else:
                display = str(value)
            md += f"| `{field_name}` | `{display}` |\n"

        # Computed properties
        md += "\n## Computed Properties\n\n"
        md += "| Property | Value |\n"
        md += "|----------|-------|\n"
        md += f"| `worker_base_url` | `{settings.worker_base_url}` |\n"
        md += f"| `ollama_base_url` | `{settings.ollama_base_url}` |\n"
        md += f"| `postgres_dsn` | `***REDACTED***` |\n"

        return md

    async def generate_status(
        self, nodes: list[DeviceInfo], services: list[ServiceInfo]
    ) -> str:
        """Generate live status snapshot."""
        md = self._doc_header("System Status")

        # Node status
        md += "## Node Status\n\n"
        md += "| Node | Type | Status | Last Seen |\n"
        md += "|------|------|--------|-----------|\n"
        for n in nodes:
            last = n.last_seen.strftime("%Y-%m-%d %H:%M") if n.last_seen else "never"
            md += f"| {n.node_id} | {n.node_type} | {n.status} | {last} |\n"

        # Service status
        md += "\n## Service Status\n\n"
        md += "| Service | Status | Host:Port |\n"
        md += "|---------|--------|----------|\n"
        for s in services:
            hp = f"{s.host}:{s.port}" if s.host else "—"
            md += f"| {s.name} | {s.status} | {hp} |\n"

        # Recent events
        md += "\n## Recent Events\n\n"
        pool = db.get_pool()
        if pool is not None:
            try:
                rows = await db.fetch_all(
                    """
                    SELECT timestamp, source, event_type, data
                    FROM elmer.events
                    ORDER BY timestamp DESC
                    LIMIT 20
                    """
                )
                if rows:
                    md += "| Time | Source | Event | Details |\n"
                    md += "|------|--------|-------|---------|\n"
                    for r in rows:
                        ts = r["timestamp"].strftime("%Y-%m-%d %H:%M")
                        data = r["data"] if isinstance(r["data"], dict) else {}
                        summary = json.dumps(data, default=str)[:80]
                        md += f"| {ts} | {r['source']} | {r['event_type']} | {summary} |\n"
                else:
                    md += "*No recent events.*\n"
            except Exception:
                md += "*Database unavailable.*\n"
        else:
            md += "*Database not connected.*\n"

        return md

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    async def generate_all(self) -> dict[str, Any]:
        """Run full discovery and generation cycle."""
        start = time.monotonic()
        now = datetime.now(timezone.utc)

        nodes = self.discover_nodes()
        services = await self.discover_services()

        docs = {
            "inventory.md": self.generate_inventory(nodes),
            "services.md": self.generate_services(services),
            "network-map.md": self.generate_network_map(nodes, services),
            "config.md": self.generate_config_summary(),
            "status.md": await self.generate_status(nodes, services),
        }

        # Ensure output directory exists.
        self._docs_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []
        changes_detected = False

        for filename, content in docs.items():
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            old_hash = self._last_snapshots.get(filename)

            if content_hash != old_hash:
                changes_detected = True

            # Write file regardless (timestamps change each run).
            path = self._docs_dir / filename
            path.write_text(content)
            files_written.append(str(path))

            self._last_snapshots[filename] = content_hash

            # Persist to elmer.documents for RAG.
            await self._store_document(
                source="autodoc",
                source_path=filename,
                title=filename.replace(".md", "").replace("-", " ").title(),
                content=content,
            )

        self._last_generation = now
        duration = time.monotonic() - start

        logger.info(
            "Auto-docs generated: %d files in %.2fs (changes=%s)",
            len(files_written),
            duration,
            changes_detected,
        )

        return {
            "generated_at": now,
            "files_written": files_written,
            "changes_detected": changes_detected,
            "duration_seconds": round(duration, 3),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    async def _store_document(
        source: str, source_path: str, title: str, content: str
    ) -> None:
        """Upsert a document row into ``elmer.documents``."""
        pool = db.get_pool()
        if pool is None:
            return
        try:
            await db.execute(
                """
                INSERT INTO elmer.documents (source, source_path, title, content, content_type, updated_at)
                VALUES ($1, $2, $3, $4, 'text/markdown', now())
                ON CONFLICT (source, source_path)
                    WHERE source IS NOT NULL AND source_path IS NOT NULL
                DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    updated_at = now()
                """,
                source,
                source_path,
                title,
                content,
            )
        except Exception:
            logger.debug(
                "Failed to store document %s/%s", source, source_path, exc_info=True
            )


# ---------------------------------------------------------------------------
# Periodic background task
# ---------------------------------------------------------------------------


async def _periodic_generation(
    documentor: SystemDocumentor,
    stop_event: asyncio.Event,
    interval_hours: float = 6.0,
) -> None:
    """Periodically regenerate all docs on a timer."""
    interval_seconds = interval_hours * 3600

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return  # stop_event was set
        except asyncio.TimeoutError:
            pass

        try:
            await documentor.generate_all()
        except Exception:
            logger.exception("Periodic doc generation failed")

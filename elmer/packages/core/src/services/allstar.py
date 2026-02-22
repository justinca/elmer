"""AllStarLink service — node status, directory lookup, and remote control.

Fetches from:
  - AllStarLink Stats API: node statistics (keyups, TX time, connections)
  - AllMon DB: node directory (callsign, description, location)
  - SSH to ShackPi: Asterisk CLI for connect/disconnect/monitor
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger("elmer.allstar")

_USER_AGENT = "Elmer/0.1 (amateur-radio-home-lab)"
_FETCH_TIMEOUT = 10.0
_SSH_TIMEOUT = 10.0

_STATS_CACHE_TTL = 60       # 60s for individual node stats
_ALLMONDB_CACHE_TTL = 900   # 15min for node directory


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class NodeStats:
    online: bool = False
    uptime_seconds: int = 0
    total_keyups: int = 0
    total_tx_time: int = 0
    total_kerchunks: int = 0
    keyed: bool = False
    version: str = ""
    last_update: str = ""

@dataclass
class LinkedNode:
    node: int = 0
    callsign: str = ""
    description: str = ""
    location: str = ""

@dataclass
class NodeInfo:
    node: int = 0
    callsign: str = ""
    description: str = ""
    location: str = ""

@dataclass
class AllStarStatus:
    node: int = 0
    callsign: str = ""
    location: str = ""
    latitude: str = ""
    longitude: str = ""
    stats: NodeStats = field(default_factory=NodeStats)
    connections: list = field(default_factory=list)
    updated: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AllStarService:
    """AllStarLink node status, directory, and remote control."""

    def __init__(self) -> None:
        self._node = settings.ALLSTAR_NODE
        self._shackpi_host = settings.ALLSTAR_SHACKPI_HOST
        self._stats_url = f"https://stats.allstarlink.org/api/stats/{self._node}"
        self._allmondb_url = "https://allmondb.allstarlink.org/allmondb.php"

        # Caches
        self._stats_cache: dict | None = None
        self._stats_cache_time: float = 0
        self._stats_lock = asyncio.Lock()

        self._allmondb_cache: dict[int, NodeInfo] | None = None
        self._allmondb_cache_time: float = 0
        self._allmondb_lock = asyncio.Lock()

    # -- Public API ---------------------------------------------------------

    async def get_status(self) -> AllStarStatus:
        """Combined node status from the AllStarLink Stats API."""
        raw = await self._fetch_stats()
        if not raw:
            return AllStarStatus(node=self._node, updated=_now_iso())

        stats_data = raw.get("stats", {}).get("data", {})
        node_data = raw.get("node", {})
        server_data = node_data.get("server", {})

        uptime = _safe_int(stats_data.get("apprptuptime", 0))
        updated_at = raw.get("stats", {}).get("updated_at", "")

        node_stats = NodeStats(
            online=bool(updated_at),
            uptime_seconds=uptime,
            total_keyups=_safe_int(stats_data.get("totalkeyups", 0)),
            total_tx_time=_safe_int(stats_data.get("totaltxtime", 0)),
            total_kerchunks=_safe_int(stats_data.get("totalkerchunks", 0)),
            keyed=bool(stats_data.get("keyed", False)),
            version=str(stats_data.get("apprptvers", "")),
            last_update=updated_at,
        )

        connections = await self._parse_connections(stats_data)

        return AllStarStatus(
            node=self._node,
            callsign=node_data.get("callsign", ""),
            location=server_data.get("Location", ""),
            latitude=str(server_data.get("Latitude", "")),
            longitude=str(server_data.get("Logitude", "")),  # API typo
            stats=asdict(node_stats),
            connections=[asdict(c) for c in connections],
            updated=updated_at,
        )

    async def get_connections(self) -> list[LinkedNode]:
        """Currently connected/linked nodes."""
        raw = await self._fetch_stats()
        if not raw:
            return []
        stats_data = raw.get("stats", {}).get("data", {})
        return await self._parse_connections(stats_data)

    async def get_node_info(self, node_number: int) -> NodeInfo | None:
        """Look up any node in the AllMon DB directory."""
        directory = await self._fetch_allmondb()
        return directory.get(node_number)

    async def connect_node(self, remote_node: int) -> dict:
        """Connect to a remote node in transceive mode (*3)."""
        return await self._rpt_fun(f"*3{remote_node}", "connect", remote_node)

    async def disconnect_node(self, remote_node: int) -> dict:
        """Disconnect from a remote node (*1)."""
        return await self._rpt_fun(f"*1{remote_node}", "disconnect", remote_node)

    async def monitor_node(self, remote_node: int) -> dict:
        """Connect to a remote node in monitor/listen-only mode (*2)."""
        return await self._rpt_fun(f"*2{remote_node}", "monitor", remote_node)

    async def get_local_status(self) -> dict:
        """Get local connection status from Asterisk CLI (*70)."""
        return await self._rpt_fun("*70", "local_status", 0)

    async def get_raw_stats(self) -> dict | None:
        """Return raw stats API response (for /allstar/stats endpoint)."""
        return await self._fetch_stats()

    def clear_cache(self) -> None:
        """Bust the stats cache so next fetch is fresh."""
        self._stats_cache_time = 0

    # -- Internal helpers ---------------------------------------------------

    async def _rpt_fun(self, dtmf: str, action: str, remote_node: int) -> dict:
        """Execute an Asterisk rpt fun command via SSH."""
        cmd = f"asterisk -rx 'rpt fun {self._node} {dtmf}'"
        stdout, stderr, rc = await self._ssh_exec(cmd)
        if rc != 0:
            logger.warning("AllStar %s failed (rc=%d): %s", action, rc, stderr)
            return {
                "status": "error",
                "action": action,
                "node": remote_node,
                "error": stderr or stdout or f"Exit code {rc}",
            }
        logger.info("AllStar %s node %d: %s", action, remote_node, stdout)
        return {
            "status": "ok",
            "action": action,
            "node": remote_node,
            "output": stdout,
        }

    async def _ssh_exec(self, command: str) -> tuple[str, str, int]:
        """Run a command on ShackPi via SSH."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh",
                "-F", "/dev/null",
                "-o", "ConnectTimeout=5",
                "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR",
                f"justin@{self._shackpi_host}",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_SSH_TIMEOUT
            )
            return (
                stdout.decode().strip(),
                stderr.decode().strip(),
                proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            logger.warning("SSH to %s timed out", self._shackpi_host)
            return "", "SSH timeout", 1
        except Exception as exc:
            logger.warning("SSH to %s failed: %s", self._shackpi_host, exc)
            return "", str(exc), 1

    async def _fetch_stats(self) -> dict | None:
        """Fetch node stats from AllStarLink API with caching."""
        async with self._stats_lock:
            now = time.monotonic()
            if (
                self._stats_cache is not None
                and now - self._stats_cache_time < _STATS_CACHE_TTL
            ):
                return self._stats_cache

            try:
                async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
                    resp = await client.get(
                        self._stats_url,
                        headers={"User-Agent": _USER_AGENT},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    self._stats_cache = data
                    self._stats_cache_time = now
                    logger.debug("Fetched AllStarLink stats for node %d", self._node)
                    return data
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning("AllStarLink stats API error: %s", exc)
                # Return stale cache if available
                if self._stats_cache is not None:
                    return self._stats_cache
                return None

    async def _fetch_allmondb(self) -> dict[int, NodeInfo]:
        """Fetch and parse the AllMon DB node directory."""
        async with self._allmondb_lock:
            now = time.monotonic()
            if (
                self._allmondb_cache is not None
                and now - self._allmondb_cache_time < _ALLMONDB_CACHE_TTL
            ):
                return self._allmondb_cache

            try:
                async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
                    resp = await client.get(
                        self._allmondb_url,
                        headers={"User-Agent": _USER_AGENT},
                    )
                    resp.raise_for_status()
                    directory = self._parse_allmondb(resp.text)
                    self._allmondb_cache = directory
                    self._allmondb_cache_time = now
                    logger.debug("Fetched AllMon DB: %d nodes", len(directory))
                    return directory
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning("AllMon DB fetch error: %s", exc)
                if self._allmondb_cache is not None:
                    return self._allmondb_cache
                return {}

    @staticmethod
    def _parse_allmondb(text: str) -> dict[int, NodeInfo]:
        """Parse pipe-delimited AllMon DB into node lookup dict."""
        directory: dict[int, NodeInfo] = {}
        for line in text.strip().splitlines():
            parts = line.split("|")
            if len(parts) < 2:
                continue
            try:
                node_num = int(parts[0].strip())
            except ValueError:
                continue
            directory[node_num] = NodeInfo(
                node=node_num,
                callsign=parts[1].strip() if len(parts) > 1 else "",
                description=parts[2].strip() if len(parts) > 2 else "",
                location=parts[3].strip() if len(parts) > 3 else "",
            )
        return directory

    async def _parse_connections(self, stats_data: dict) -> list[LinkedNode]:
        """Parse linked nodes from stats API data.

        The AllStarLink Stats API returns:
          - linkedNodes: list of full node objects [{name: 401955, callsign: ..., server: {Location: ...}}, ...]
          - links: list of node number strings ["401955", ...]
        """
        connected: list[LinkedNode] = []
        seen: set[int] = set()

        # linkedNodes contains full node detail objects
        linked_nodes = stats_data.get("linkedNodes") or []
        if isinstance(linked_nodes, list):
            for item in linked_nodes:
                if isinstance(item, dict):
                    node_num = _safe_int(item.get("name", 0))
                    if not node_num or node_num in seen:
                        continue
                    seen.add(node_num)
                    server = item.get("server") or {}
                    connected.append(LinkedNode(
                        node=node_num,
                        callsign=item.get("callsign", ""),
                        description=server.get("SiteName", "") or server.get("Server_Name", ""),
                        location=server.get("Location", ""),
                    ))

        # links contains node number strings — use as fallback for any
        # nodes not already covered by linkedNodes
        links = stats_data.get("links") or []
        if isinstance(links, list):
            for item in links:
                node_num = _safe_int(item)
                if not node_num or node_num in seen:
                    continue
                seen.add(node_num)
                info = await self.get_node_info(node_num)
                connected.append(LinkedNode(
                    node=node_num,
                    callsign=info.callsign if info else "",
                    description=info.description if info else "",
                    location=info.location if info else "",
                ))

        return connected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(value: Any) -> int:
    """Safely convert a value to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: AllStarService | None = None


def get_service() -> AllStarService:
    global _service
    if _service is None:
        _service = AllStarService()
    return _service

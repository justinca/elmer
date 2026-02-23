"""AllStarLink service — node status, directory lookup, and remote control.

Fetches from:
  - AllStarLink Stats API: node statistics (keyups, TX time, connections)
  - AllMon DB: node directory (callsign, description, location)
  - AllStarLink Nodelist: searchable node directory (location, site, affiliation)
  - AllStarLink Keyed Nodes: currently transmitting nodes
  - SSH to ShackPi: Asterisk CLI for connect/disconnect/monitor
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger("elmer.allstar")

_USER_AGENT = "Elmer/0.1 (amateur-radio-home-lab)"
_FETCH_TIMEOUT = 10.0
_SSH_TIMEOUT = 10.0

_STATS_CACHE_TTL = 60       # 60s for individual node stats
_ALLMONDB_CACHE_TTL = 900   # 15min for node directory
_KEYED_CACHE_TTL = 60       # 60s for keyed nodes
_NODELIST_CACHE_TTL = 900   # 15min for full nodelist
_NODELIST_FETCH_TIMEOUT = 30.0  # nodelist JSON is ~3MB


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
class NodeListEntry:
    """Rich node info from the allstarlink.org nodelist."""
    node: int = 0
    callsign: str = ""
    owner: str = ""
    frequency: str = ""
    tone: str = ""
    location: str = ""
    site: str = ""
    affiliation: str = ""

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

        self._keyed_cache: list[dict] | None = None
        self._keyed_cache_time: float = 0
        self._keyed_lock = asyncio.Lock()

        self._nodelist_cache: list[dict] | None = None
        self._nodelist_cache_time: float = 0
        self._nodelist_lock = asyncio.Lock()

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

    async def get_keyed_nodes(self) -> list[dict]:
        """Fetch currently keyed (transmitting) nodes from stats page."""
        return await self._fetch_keyed()

    async def search_nodes(self, query: str, limit: int = 20) -> list[NodeListEntry]:
        """Search for nodes by location, callsign, site, or affiliation.

        Uses the allstarlink.org nodelist JSON endpoint (rich data with
        location, site, affiliation) with fallback to AllMon DB.
        """
        results = await self._search_nodelist(query, limit)
        if results:
            return results
        return await self._search_allmondb(query, limit)

    def clear_cache(self) -> None:
        """Bust the stats cache so next fetch is fresh."""
        self._stats_cache_time = 0

    # -- Internal helpers ---------------------------------------------------

    async def _rpt_fun(self, dtmf: str, action: str, remote_node: int) -> dict:
        """Execute an Asterisk rpt fun command via SSH."""
        cmd = f"sudo /usr/sbin/asterisk -rx 'rpt fun {self._node} {dtmf}'"
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

    async def _fetch_keyed(self) -> list[dict]:
        """Fetch and parse keyed nodes HTML from stats.allstarlink.org."""
        async with self._keyed_lock:
            now = time.monotonic()
            if (
                self._keyed_cache is not None
                and now - self._keyed_cache_time < _KEYED_CACHE_TTL
            ):
                return self._keyed_cache

            try:
                async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
                    resp = await client.get(
                        "https://stats.allstarlink.org/stats/keyed",
                        headers={"User-Agent": _USER_AGENT},
                    )
                    resp.raise_for_status()
                    parser = _KeyedNodesParser()
                    parser.feed(resp.text)
                    self._keyed_cache = parser.nodes
                    self._keyed_cache_time = now
                    logger.debug("Fetched keyed nodes: %d active", len(parser.nodes))
                    return self._keyed_cache
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning("Keyed nodes fetch error: %s", exc)
                if self._keyed_cache is not None:
                    return self._keyed_cache
                return []

    async def _fetch_nodelist(self) -> list[dict]:
        """Fetch the full nodelist JSON from allstarlink.org."""
        async with self._nodelist_lock:
            now = time.monotonic()
            if (
                self._nodelist_cache is not None
                and now - self._nodelist_cache_time < _NODELIST_CACHE_TTL
            ):
                return self._nodelist_cache

            try:
                async with httpx.AsyncClient(timeout=_NODELIST_FETCH_TIMEOUT) as client:
                    resp = await client.get(
                        "https://www.allstarlink.org/nodelist/nodelist-server.php?age=7",
                        headers={"User-Agent": _USER_AGENT},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    self._nodelist_cache = data
                    self._nodelist_cache_time = now
                    logger.debug("Fetched nodelist: %d nodes", len(data))
                    return data
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning("Nodelist fetch error: %s", exc)
                if self._nodelist_cache is not None:
                    return self._nodelist_cache
                return []

    async def _search_nodelist(self, query: str, limit: int = 20) -> list[NodeListEntry]:
        """Search the nodelist JSON by keyword across multiple fields."""
        data = await self._fetch_nodelist()
        if not data:
            return []

        q = query.lower()
        matches: list[NodeListEntry] = []
        for entry in data:
            searchable = " ".join([
                str(entry.get("Location", "")),
                str(entry.get("SiteName", "")),
                str(entry.get("callsign", "")),
                str(entry.get("Affiliation", "")),
                str(entry.get("User_ID", "")),
                str(entry.get("node_frequency", "")),
            ]).lower()
            if q in searchable:
                matches.append(NodeListEntry(
                    node=_safe_int(entry.get("name", 0)),
                    callsign=str(entry.get("callsign", "")),
                    owner=str(entry.get("User_ID", "")),
                    frequency=str(entry.get("node_frequency", "")),
                    tone=str(entry.get("node_tone", "")),
                    location=str(entry.get("Location", "")),
                    site=str(entry.get("SiteName", "")),
                    affiliation=str(entry.get("Affiliation", "")),
                ))
                if len(matches) >= limit:
                    break
        return matches

    async def _search_allmondb(self, query: str, limit: int = 20) -> list[NodeListEntry]:
        """Fallback: search AllMon DB cache by keyword."""
        directory = await self._fetch_allmondb()
        if not directory:
            return []

        q = query.lower()
        matches: list[NodeListEntry] = []
        for info in directory.values():
            searchable = f"{info.callsign} {info.description} {info.location}".lower()
            if q in searchable:
                matches.append(NodeListEntry(
                    node=info.node,
                    callsign=info.callsign,
                    location=info.location,
                    site=info.description,
                ))
                if len(matches) >= limit:
                    break
        return matches

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
                    # Build a useful description from available fields.
                    # node_frequency often has the best label (e.g. "NW AllStar Group").
                    desc = (
                        str(item.get("node_frequency", "") or "").strip()
                        or server.get("SiteName", "")
                        or server.get("Location", "")
                        or server.get("Server_Name", "")
                    )
                    connected.append(LinkedNode(
                        node=node_num,
                        callsign=item.get("callsign", ""),
                        description=desc,
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
# HTML parser for keyed nodes page
# ---------------------------------------------------------------------------

class _KeyedNodesParser(HTMLParser):
    """Parse the keyed nodes HTML table from stats.allstarlink.org/stats/keyed."""

    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[dict] = []
        self._in_tbody = False
        self._in_row = False
        self._in_cell = False
        self._cells: list[str] = []
        self._current_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tbody":
            self._in_tbody = True
        elif tag == "tr" and self._in_tbody:
            self._in_row = True
            self._cells = []
        elif tag == "td" and self._in_row:
            self._in_cell = True
            self._current_text = ""
        elif tag == "a" and self._in_cell:
            # Links inside cells contain node numbers and callsigns
            pass

    def handle_endtag(self, tag: str) -> None:
        if tag == "tbody":
            self._in_tbody = False
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if len(self._cells) >= 7:
                # Columns: Node, Chart, Callsign, Frequency, CTCSS, Location, Connected
                node_num = _safe_int(self._cells[0].strip())
                if node_num:
                    connected = [
                        _safe_int(n.strip())
                        for n in re.split(r"[\s,]+", self._cells[6].strip())
                        if _safe_int(n.strip())
                    ]
                    self.nodes.append({
                        "node": node_num,
                        "callsign": self._cells[2].strip(),
                        "frequency": self._cells[3].strip(),
                        "ctcss": self._cells[4].strip(),
                        "location": self._cells[5].strip(),
                        "connected": connected,
                    })
        elif tag == "td" and self._in_cell:
            self._in_cell = False
            self._cells.append(self._current_text)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_text += data


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

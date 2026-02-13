"""DX Cluster telnet client — connects, parses spots, persists, publishes.

Handles AR-Cluster, DX Spider, and CC Cluster spot formats.  Auto-reconnects
on disconnect.  Stores spots in ``elmer.dx_spots`` and publishes each to
``elmer/dx/spot`` via MQTT.
"""

import asyncio
import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from ..services import db
from .mqtt_service import publish as mqtt_publish
from .callsign_lookup import get_lookup

logger = logging.getLogger("elmer.dx_cluster")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_RECONNECT_DELAY = 30       # seconds between reconnect attempts
_KEEPALIVE_INTERVAL = 300   # send a keepalive every 5 minutes
_SUMMARY_INTERVAL = 300     # publish summary every 5 minutes
_MAX_MEM_SPOTS = 500        # keep last N spots in memory
_PRUNE_INTERVAL = 3600      # prune old DB spots every hour

# ---------------------------------------------------------------------------
# Band plan — frequency (kHz) to band
# ---------------------------------------------------------------------------

_BAND_EDGES = [
    (1800, 2000, "160m"),
    (3500, 4000, "80m"),
    (5330, 5410, "60m"),
    (7000, 7300, "40m"),
    (10100, 10150, "30m"),
    (14000, 14350, "20m"),
    (18068, 18168, "17m"),
    (21000, 21450, "15m"),
    (24890, 24990, "12m"),
    (28000, 29700, "10m"),
    (50000, 54000, "6m"),
    (144000, 148000, "2m"),
    (420000, 450000, "70cm"),
]


def freq_to_band(freq_khz: float) -> str:
    """Convert frequency in kHz to band name."""
    for low, high, band in _BAND_EDGES:
        if low <= freq_khz <= high:
            return band
    return "unknown"


def freq_to_mode(freq_khz: float) -> str:
    """Guess mode from frequency (band plan conventions)."""
    # CW portions (lower part of most bands)
    cw_ranges = [
        (1800, 1850), (3500, 3600), (7000, 7050),
        (10100, 10130), (14000, 14070), (18068, 18095),
        (21000, 21070), (24890, 24920), (28000, 28070),
    ]
    for low, high in cw_ranges:
        if low <= freq_khz <= high:
            return "CW"

    # Digital / FT8 / FT4 portions
    digital_ranges = [
        (1840, 1843), (3573, 3575), (5357, 5358),
        (7074, 7076), (10136, 10138), (14074, 14076),
        (18100, 18102), (21074, 21076), (24915, 24917),
        (28074, 28076), (50313, 50315), (50323, 50325),
    ]
    for low, high in digital_ranges:
        if low <= freq_khz <= high:
            return "FT8"

    # RTTY
    rtty_ranges = [
        (3580, 3600), (7035, 7045), (14080, 14100),
        (21080, 21100), (28080, 28100),
    ]
    for low, high in rtty_ranges:
        if low <= freq_khz <= high:
            return "RTTY"

    # SSB/Phone (upper portions)
    return "SSB"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DXSpot:
    spotter_call: str = ""
    dx_call: str = ""
    frequency: float = 0.0
    band: str = ""
    mode: str = ""
    comment: str = ""
    time: str = ""
    spotter_grid: str = ""
    dx_grid: str = ""
    dx_entity: str = ""


# ---------------------------------------------------------------------------
# Spot parser — handles multiple cluster formats
# ---------------------------------------------------------------------------

# Common DX spot format (AR-Cluster, DX Spider, CC Cluster):
# DX de W3LPL:     14074.0  FT5W         FT8 -20 dB 1632Z
# DX de KE3X:      21074.0  HZ1TT        FT8 Heard in EN           1633Z
_DX_PATTERN = re.compile(
    r"^DX\s+de\s+"
    r"(?P<spotter>[A-Z0-9/]+)\s*:\s*"
    r"(?P<freq>[\d.]+)\s+"
    r"(?P<dx_call>[A-Z0-9/]+)\s+"
    r"(?P<comment>.*?)\s+"
    r"(?P<time>\d{4})Z?\s*$",
    re.IGNORECASE,
)

# Some clusters use a slightly different format:
# DX de W3LPL:      14074.0  FT5W         FT8                1632Z EN
_DX_PATTERN_ALT = re.compile(
    r"^DX\s+de\s+"
    r"(?P<spotter>[A-Z0-9/]+)\s*:\s*"
    r"(?P<freq>[\d.]+)\s+"
    r"(?P<dx_call>[A-Z0-9/]+)\s*"
    r"(?P<comment>.*)",
    re.IGNORECASE,
)


def parse_spot(line: str) -> DXSpot | None:
    """Parse a DX cluster spot line into a DXSpot object."""
    line = line.strip()
    if not line.upper().startswith("DX DE "):
        return None

    m = _DX_PATTERN.match(line)
    if m is None:
        m = _DX_PATTERN_ALT.match(line)
    if m is None:
        return None

    freq = float(m.group("freq"))
    comment = m.group("comment").strip()
    spot_time = m.group("time") if "time" in m.groupdict() else ""

    # Extract mode from comment if present.
    mode = ""
    comment_upper = comment.upper()
    for m_name in ("FT8", "FT4", "CW", "SSB", "RTTY", "PSK", "JT65", "JS8",
                   "DSTAR", "FM", "AM", "SSTV", "WSPR"):
        if m_name in comment_upper:
            mode = m_name
            break

    if not mode:
        mode = freq_to_mode(freq)

    band = freq_to_band(freq)

    # Try to extract grid squares from comment.
    grids = re.findall(r"\b([A-R]{2}\d{2}[a-x]{0,2})\b", comment, re.IGNORECASE)
    spotter_grid = ""
    dx_grid = ""
    if len(grids) >= 2:
        dx_grid = grids[0].upper()
        spotter_grid = grids[1].upper()
    elif len(grids) == 1:
        dx_grid = grids[0].upper()

    # DXCC entity lookup.
    dx_call = m.group("dx_call").upper()
    lookup = get_lookup()
    entity = lookup.get_entity(dx_call)
    entity_name = entity.entity_name if entity else ""

    # Format time.
    now = datetime.now(timezone.utc)
    if spot_time and len(spot_time) == 4:
        try:
            hour, minute = int(spot_time[:2]), int(spot_time[2:])
            ts = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # If the time is in the future, it's from yesterday.
            if ts > now:
                ts = ts.replace(day=ts.day - 1)
            time_str = ts.isoformat()
        except (ValueError, OverflowError):
            time_str = now.isoformat()
    else:
        time_str = now.isoformat()

    return DXSpot(
        spotter_call=m.group("spotter").upper(),
        dx_call=dx_call,
        frequency=freq,
        band=band,
        mode=mode,
        comment=comment,
        time=time_str,
        spotter_grid=spotter_grid,
        dx_grid=dx_grid,
        dx_entity=entity_name,
    )


# ---------------------------------------------------------------------------
# DXClusterClient
# ---------------------------------------------------------------------------

class DXClusterClient:
    """Async telnet client for DX cluster connections."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        callsign: str | None = None,
    ) -> None:
        self.host = host or settings.DX_CLUSTER_HOST
        self.port = port or settings.DX_CLUSTER_PORT
        self.callsign = callsign or settings.DX_CLUSTER_CALLSIGN
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._running = False
        self._task: asyncio.Task | None = None
        self._spots: deque[DXSpot] = deque(maxlen=_MAX_MEM_SPOTS)
        self._spot_count = 0
        self._last_prune = 0.0
        self._last_summary = 0.0

    # -- Public API ---------------------------------------------------------

    async def connect(self) -> None:
        """Start the background read loop (connects and auto-reconnects)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("DX cluster client started (target: %s:%d)", self.host, self.port)

    async def disconnect(self) -> None:
        """Stop the client and close the connection."""
        self._running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._connected = False
        logger.info("DX cluster client stopped")

    def get_status(self) -> dict[str, Any]:
        """Return connection status."""
        return {
            "connected": self._connected,
            "host": self.host,
            "port": self.port,
            "callsign": self.callsign,
            "spots_in_memory": len(self._spots),
            "total_spots_received": self._spot_count,
        }

    def get_recent_spots(
        self,
        limit: int = 50,
        band: str | None = None,
        mode: str | None = None,
    ) -> list[DXSpot]:
        """Get recent spots from in-memory buffer."""
        spots = list(self._spots)
        if band:
            spots = [s for s in spots if s.band == band]
        if mode:
            spots = [s for s in spots if s.mode.upper() == mode.upper()]
        return spots[-limit:]

    def get_spots_for_entity(self, entity: str) -> list[DXSpot]:
        """Get spots for a specific DXCC entity from memory."""
        entity_lower = entity.lower()
        return [
            s for s in self._spots
            if s.dx_entity.lower() == entity_lower
        ]

    async def send_command(self, cmd: str) -> None:
        """Send a raw command to the cluster."""
        if self._writer and self._connected:
            try:
                self._writer.write(f"{cmd}\r\n".encode("ascii", errors="replace"))
                await self._writer.drain()
            except Exception:
                logger.warning("Failed to send command: %s", cmd)

    # -- Connection loop ----------------------------------------------------

    async def _run_loop(self) -> None:
        """Main loop: connect, read, reconnect."""
        while self._running:
            try:
                await self._do_connect()
                await self._read_loop()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("DX cluster connection error")

            self._connected = False
            if self._running:
                logger.info(
                    "DX cluster disconnected, reconnecting in %ds...",
                    _RECONNECT_DELAY,
                )
                await asyncio.sleep(_RECONNECT_DELAY)

    async def _do_connect(self) -> None:
        """Establish telnet connection and handle login."""
        logger.info("Connecting to DX cluster %s:%d...", self.host, self.port)
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=30.0,
        )

        # Read initial banner and respond to login prompt.
        login_done = False
        deadline = asyncio.get_event_loop().time() + 15.0

        while asyncio.get_event_loop().time() < deadline:
            try:
                data = await asyncio.wait_for(
                    self._reader.readline(), timeout=5.0,
                )
            except asyncio.TimeoutError:
                if not login_done:
                    # Some clusters don't send a prompt, just send callsign.
                    self._writer.write(
                        f"{self.callsign}\r\n".encode("ascii", errors="replace")
                    )
                    await self._writer.drain()
                    login_done = True
                continue

            line = data.decode("ascii", errors="replace").strip()
            if not line:
                continue

            logger.debug("Cluster banner: %s", line[:120])

            # Look for login/callsign prompt.
            line_lower = line.lower()
            if any(kw in line_lower for kw in (
                "login:", "call:", "callsign:", "enter your call",
                "please enter your call", "your call",
            )):
                self._writer.write(
                    f"{self.callsign}\r\n".encode("ascii", errors="replace")
                )
                await self._writer.drain()
                login_done = True
                logger.info("Sent callsign %s to cluster", self.callsign)
                continue

            # Welcome message usually means login succeeded.
            if login_done and any(kw in line_lower for kw in (
                "hello", "welcome", "de ", "connected",
            )):
                break

        self._connected = True
        logger.info("Connected to DX cluster %s:%d as %s",
                     self.host, self.port, self.callsign)

        # Enable FT8/FT4/Skimmer spots on CC Cluster nodes.
        for cmd in ("SET/FT8", "SET/FT4", "SET/SKIMMER"):
            await asyncio.sleep(0.5)
            await self.send_command(cmd)
        logger.info("Sent SET/FT8, SET/FT4, SET/SKIMMER to cluster")

    async def _read_loop(self) -> None:
        """Read lines from the cluster and process spots."""
        keepalive_deadline = time.monotonic() + _KEEPALIVE_INTERVAL

        while self._running and self._reader:
            try:
                data = await asyncio.wait_for(
                    self._reader.readline(), timeout=60.0,
                )
            except asyncio.TimeoutError:
                # Send keepalive.
                if time.monotonic() >= keepalive_deadline:
                    await self.send_command("")
                    keepalive_deadline = time.monotonic() + _KEEPALIVE_INTERVAL
                continue

            if not data:
                # Connection closed by remote.
                logger.warning("DX cluster connection closed by remote")
                return

            line = data.decode("ascii", errors="replace").strip()
            if not line:
                continue

            # Try to parse as a DX spot.
            spot = parse_spot(line)
            if spot:
                await self._handle_spot(spot, line)
                continue

            # Log other interesting lines.
            if not line.startswith(">") and len(line) > 5:
                logger.debug("Cluster: %s", line[:120])

            # Periodic tasks.
            now = time.monotonic()
            if now >= keepalive_deadline:
                await self.send_command("")
                keepalive_deadline = now + _KEEPALIVE_INTERVAL

            if now - self._last_summary >= _SUMMARY_INTERVAL:
                asyncio.create_task(self._publish_summary())
                self._last_summary = now

            if now - self._last_prune >= _PRUNE_INTERVAL:
                asyncio.create_task(self._prune_old_spots())
                self._last_prune = now

    # -- Spot handling ------------------------------------------------------

    async def _handle_spot(self, spot: DXSpot, raw: str) -> None:
        """Process a parsed spot: store in memory, persist, publish."""
        self._spots.append(spot)
        self._spot_count += 1

        # Persist to database.
        try:
            await db.execute(
                """
                INSERT INTO elmer.dx_spots
                    (timestamp, spotter, dx_call, frequency, band, mode,
                     comment, dx_entity, raw_spot)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                datetime.fromisoformat(spot.time),
                spot.spotter_call,
                spot.dx_call,
                spot.frequency,
                spot.band,
                spot.mode,
                spot.comment,
                spot.dx_entity,
                raw,
            )
        except Exception:
            logger.debug("Failed to persist DX spot", exc_info=True)

        # Publish to MQTT (pass dict — mqtt_publish handles serialisation).
        try:
            await mqtt_publish(
                "elmer/dx/spot",
                asdict(spot),
            )
        except Exception:
            logger.debug("Failed to publish DX spot to MQTT")

        if self._spot_count % 100 == 0:
            logger.info("DX cluster: %d spots received", self._spot_count)

    async def _publish_summary(self) -> None:
        """Publish a band activity summary to MQTT."""
        band_counts: dict[str, int] = {}
        mode_counts: dict[str, int] = {}

        # Count from in-memory buffer.
        for spot in self._spots:
            band_counts[spot.band] = band_counts.get(spot.band, 0) + 1
            mode_counts[spot.mode] = mode_counts.get(spot.mode, 0) + 1

        summary = {
            "total_spots": len(self._spots),
            "total_received": self._spot_count,
            "connected": self._connected,
            "bands": band_counts,
            "modes": mode_counts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await mqtt_publish(
                "elmer/dx/summary",
                summary,
            )
        except Exception:
            logger.debug("Failed to publish DX summary")

    async def _prune_old_spots(self) -> None:
        """Delete spots older than retention period from the database."""
        hours = settings.DX_SPOT_RETENTION_HOURS
        try:
            result = await db.execute(
                "DELETE FROM elmer.dx_spots WHERE timestamp < now() - make_interval(hours => $1)",
                hours,
            )
            logger.info("Pruned old DX spots (retention: %dh): %s", hours, result)
        except Exception:
            logger.debug("Failed to prune old spots", exc_info=True)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client: DXClusterClient | None = None


def get_client() -> DXClusterClient:
    global _client
    if _client is None:
        _client = DXClusterClient()
    return _client

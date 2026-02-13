"""Propagation data service — collects solar and band condition data.

Fetches from:
  - NOAA/SWPC: solar flux, K-index, A-index, X-ray flux, sunspot number
  - HamQSL (N0NBH): band conditions, geomagnetic field, signal noise
  - NOAA DRAP: D-Region absorption / affected frequencies

Caches data in memory (15-min TTL) and persists snapshots to the
``elmer.propagation_data`` table for historical queries.
"""

import asyncio
import json
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

import httpx

from ..services import db
from .mqtt_service import publish as mqtt_publish

logger = logging.getLogger("elmer.propagation")

_USER_AGENT = "Elmer/0.1 (amateur-radio-home-lab; github.com/justinca/elmer)"
_FETCH_TIMEOUT = 10.0  # seconds per source
_CACHE_TTL = 900  # 15 minutes


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SolarData:
    solar_flux: float | None = None
    sunspot_number: int | None = None
    a_index: int | None = None
    k_index: float | None = None
    x_ray_flux: str | None = None
    proton_flux: str | None = None
    geomag_storm: str | None = None
    solar_wind: float | None = None
    magnetic_field: float | None = None
    geomag_field: str | None = None
    signal_noise: str | None = None


@dataclass
class BandCondition:
    band: str = ""
    day: str = ""      # "Good", "Fair", "Poor"
    night: str = ""    # "Good", "Fair", "Poor"


@dataclass
class VHFCondition:
    name: str = ""
    location: str = ""
    status: str = ""


@dataclass
class PropagationForecast:
    source: str = "hamqsl"
    geomag_field: str = ""
    signal_noise: str = ""
    muf: str = ""
    solar_flux_trend: str = ""
    k_index_trend: str = ""
    updated: str = ""


@dataclass
class PropagationSnapshot:
    timestamp: str = ""
    solar_flux: float | None = None
    sunspot_number: int | None = None
    a_index: int | None = None
    k_index: float | None = None
    x_ray_flux: str | None = None
    geomag_storm: str | None = None
    band_conditions: dict | None = None


@dataclass
class PropagationConditions:
    solar: SolarData = field(default_factory=SolarData)
    bands: dict[str, BandCondition] = field(default_factory=dict)
    vhf: list[VHFCondition] = field(default_factory=list)
    forecast: PropagationForecast = field(default_factory=PropagationForecast)
    drap: dict[str, Any] = field(default_factory=dict)
    updated: str = ""
    source_status: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Band mapping — expand grouped bands from HamQSL into individual bands
# ---------------------------------------------------------------------------

_BAND_GROUP_MAP = {
    "80m-40m": ["160m", "80m", "60m", "40m"],
    "30m-20m": ["30m", "20m"],
    "17m-15m": ["17m", "15m"],
    "12m-10m": ["12m", "10m", "6m"],
}

ALL_BANDS = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]


# ---------------------------------------------------------------------------
# PropagationService
# ---------------------------------------------------------------------------

class PropagationService:
    """Fetches, caches, and stores propagation data."""

    def __init__(self) -> None:
        self._cache: PropagationConditions | None = None
        self._cache_time: float = 0.0
        self._prev_conditions: PropagationConditions | None = None
        self._lock = asyncio.Lock()

    # -- Public API ---------------------------------------------------------

    async def get_current_conditions(self) -> PropagationConditions:
        """Return comprehensive current conditions (from cache if fresh)."""
        if self._cache is not None and (time.monotonic() - self._cache_time) < _CACHE_TTL:
            return self._cache
        return await self.refresh()

    async def get_band_conditions(self) -> dict[str, dict]:
        """Per-band conditions dict."""
        conditions = await self.get_current_conditions()
        return {name: asdict(bc) for name, bc in conditions.bands.items()}

    async def get_solar_data(self) -> dict:
        """Solar indices as dict."""
        conditions = await self.get_current_conditions()
        return asdict(conditions.solar)

    async def get_forecast(self) -> dict:
        """Forecast data as dict."""
        conditions = await self.get_current_conditions()
        return asdict(conditions.forecast)

    async def get_history(self, hours: int = 24) -> list[dict]:
        """Historical data points from the database."""
        try:
            rows = await db.fetch_all(
                """
                SELECT timestamp, solar_flux, sunspot_number, a_index, k_index,
                       x_ray_flux, geomag_storm, band_conditions
                FROM elmer.propagation_data
                WHERE timestamp > now() - make_interval(hours => $1)
                ORDER BY timestamp DESC
                """,
                hours,
            )
            return [
                {
                    "timestamp": str(r["timestamp"]),
                    "solar_flux": r["solar_flux"],
                    "sunspot_number": r["sunspot_number"],
                    "a_index": r["a_index"],
                    "k_index": r["k_index"],
                    "x_ray_flux": r["x_ray_flux"],
                    "geomag_storm": r["geomag_storm"],
                    "band_conditions": (
                        json.loads(r["band_conditions"])
                        if isinstance(r["band_conditions"], str)
                        else r["band_conditions"]
                    ),
                }
                for r in rows
            ]
        except Exception:
            logger.warning("Failed to fetch propagation history", exc_info=True)
            return []

    async def get_band_detail(self, band: str) -> dict | None:
        """Detail for a specific band including history."""
        conditions = await self.get_current_conditions()
        bc = conditions.bands.get(band)
        if bc is None:
            return None

        # Get recent history for this band.
        history = await self.get_history(hours=48)
        band_history = []
        for h in history:
            bc_data = h.get("band_conditions") or {}
            if band in bc_data:
                band_history.append({
                    "timestamp": h["timestamp"],
                    "day": bc_data[band].get("day", ""),
                    "night": bc_data[band].get("night", ""),
                })

        return {
            "band": band,
            "day": bc.day,
            "night": bc.night,
            "solar_flux": conditions.solar.solar_flux,
            "k_index": conditions.solar.k_index,
            "history": band_history[:20],
        }

    # -- Refresh / fetch ----------------------------------------------------

    async def refresh(self) -> PropagationConditions:
        """Fetch all sources, update cache, persist, check alerts."""
        async with self._lock:
            conditions = PropagationConditions(
                updated=datetime.now(timezone.utc).isoformat(),
            )

            # Fetch all sources concurrently.
            results = await asyncio.gather(
                self._fetch_hamqsl(),
                self._fetch_k_index(),
                self._fetch_solar_cycle(),
                self._fetch_drap(),
                return_exceptions=True,
            )

            hamqsl, k_index, solar_cycle, drap = results

            # Process HamQSL (primary source for most data).
            if isinstance(hamqsl, dict):
                conditions.source_status["hamqsl"] = "ok"
                self._apply_hamqsl(conditions, hamqsl)
            else:
                conditions.source_status["hamqsl"] = f"error: {hamqsl}"
                logger.warning("HamQSL fetch failed: %s", hamqsl)

            # Process NOAA K-index (overrides HamQSL K if available).
            if isinstance(k_index, dict):
                conditions.source_status["noaa_k_index"] = "ok"
                self._apply_k_index(conditions, k_index)
            else:
                conditions.source_status["noaa_k_index"] = f"error: {k_index}"
                logger.warning("NOAA K-index fetch failed: %s", k_index)

            # Process solar cycle data.
            if isinstance(solar_cycle, dict):
                conditions.source_status["noaa_solar_cycle"] = "ok"
                self._apply_solar_cycle(conditions, solar_cycle)
            else:
                conditions.source_status["noaa_solar_cycle"] = f"error: {solar_cycle}"

            # Process DRAP.
            if isinstance(drap, dict):
                conditions.source_status["noaa_drap"] = "ok"
                conditions.drap = drap
            else:
                conditions.source_status["noaa_drap"] = f"error: {drap}"

            # Determine geomagnetic storm level from K-index.
            if conditions.solar.k_index is not None:
                conditions.solar.geomag_storm = self._k_to_storm(
                    conditions.solar.k_index
                )

            # Save previous for alert comparison.
            prev = self._prev_conditions

            # Update cache.
            self._prev_conditions = self._cache
            self._cache = conditions
            self._cache_time = time.monotonic()

            # Persist and publish (fire-and-forget).
            asyncio.create_task(self._persist_and_publish(conditions, prev))

            return conditions

    # -- Data source fetchers -----------------------------------------------

    async def _fetch_hamqsl(self) -> dict:
        """Fetch solar/band data from hamqsl.com XML feed."""
        url = "https://www.hamqsl.com/solarxml.php"
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        sd = root.find(".//solardata")
        if sd is None:
            raise ValueError("No <solardata> element in HamQSL response")

        def _text(tag: str) -> str:
            el = sd.find(tag)
            return (el.text or "").strip() if el is not None else ""

        data: dict[str, Any] = {
            "solar_flux": _text("solarflux"),
            "a_index": _text("aindex"),
            "k_index": _text("kindex"),
            "x_ray": _text("xray"),
            "sunspots": _text("sunspots"),
            "proton_flux": _text("protonflux"),
            "solar_wind": _text("solarwind"),
            "magnetic_field": _text("magneticfield"),
            "geomag_field": _text("geomagfield"),
            "signal_noise": _text("signalnoise"),
            "muf": _text("muf"),
            "updated": _text("updated"),
            "bands": {},
            "vhf": [],
        }

        # Parse band conditions.
        for band_el in sd.findall(".//calculatedconditions/band"):
            name = band_el.get("name", "")
            time_of_day = band_el.get("time", "")
            condition = (band_el.text or "").strip()
            if name not in data["bands"]:
                data["bands"][name] = {}
            data["bands"][name][time_of_day] = condition

        # Parse VHF conditions.
        for phenom in sd.findall(".//calculatedvhfconditions/phenomenon"):
            data["vhf"].append({
                "name": phenom.get("name", ""),
                "location": phenom.get("location", ""),
                "status": (phenom.text or "").strip(),
            })

        return data

    async def _fetch_k_index(self) -> dict:
        """Fetch latest planetary K-index from NOAA."""
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()

        rows = resp.json()
        if len(rows) < 2:
            raise ValueError("No K-index data rows")

        # Last row is most recent.
        latest = rows[-1]
        # Header: ["time_tag", "Kp", "a_running", "station_count"]
        return {
            "time_tag": latest[0],
            "kp": latest[1],
            "a_running": latest[2],
            "station_count": latest[3],
        }

    async def _fetch_solar_cycle(self) -> dict:
        """Fetch latest solar cycle indices from NOAA."""
        url = "https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json"
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()

        data = resp.json()
        if not data:
            raise ValueError("Empty solar cycle data")

        latest = data[-1]
        return {
            "time_tag": latest.get("time-tag", ""),
            "ssn": latest.get("ssn"),
            "smoothed_ssn": latest.get("smoothed_ssn"),
            "f10_7": latest.get("f10.7"),
            "smoothed_f10_7": latest.get("smoothed_f10.7"),
        }

    async def _fetch_drap(self) -> dict:
        """Fetch DRAP (D-Region Absorption) data.

        The file is a lat/lon grid where each cell is the Highest Affected
        Frequency (HAF) in MHz at that point.  We extract the status messages
        and the global max HAF.
        """
        url = "https://services.swpc.noaa.gov/text/drap_global_frequencies.txt"
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()

        result: dict[str, Any] = {
            "xray_message": "",
            "xray_warning": "",
            "proton_message": "",
            "proton_warning": "",
            "max_haf_mhz": 0.0,
            "absorption_active": False,
        }

        max_haf = 0.0
        for line in resp.text.splitlines():
            stripped = line.strip()

            # Extract status messages from comments.
            if stripped.startswith("#  X-RAY Message"):
                result["xray_message"] = stripped.split(":", 1)[-1].strip()
            elif stripped.startswith("#  X-RAY Warning"):
                result["xray_warning"] = stripped.split(":", 1)[-1].strip()
            elif stripped.startswith("#  Proton Message"):
                result["proton_message"] = stripped.split(":", 1)[-1].strip()
            elif stripped.startswith("#  Proton Warning"):
                result["proton_warning"] = stripped.split(":", 1)[-1].strip()
            elif stripped.startswith("#") or stripped.startswith("-") or not stripped:
                continue
            else:
                # Data row: "lat | val val val ..."
                if "|" in stripped:
                    _, values_str = stripped.split("|", 1)
                    for val_str in values_str.split():
                        try:
                            val = float(val_str)
                            if val > max_haf:
                                max_haf = val
                        except ValueError:
                            continue

        result["max_haf_mhz"] = round(max_haf, 1)
        result["absorption_active"] = max_haf > 1.0  # >1 MHz means HF impact

        return result

    # -- Apply fetched data to conditions -----------------------------------

    def _apply_hamqsl(self, conditions: PropagationConditions, data: dict) -> None:
        """Apply HamQSL data to conditions object."""
        solar = conditions.solar

        solar.solar_flux = self._safe_float(data.get("solar_flux"))
        solar.a_index = self._safe_int(data.get("a_index"))
        solar.k_index = self._safe_float(data.get("k_index"))
        solar.x_ray_flux = data.get("x_ray") or None
        solar.sunspot_number = self._safe_int(data.get("sunspots"))
        solar.proton_flux = data.get("proton_flux") or None
        solar.solar_wind = self._safe_float(data.get("solar_wind"))
        solar.magnetic_field = self._safe_float(data.get("magnetic_field"))
        solar.geomag_field = data.get("geomag_field") or None
        solar.signal_noise = data.get("signal_noise") or None

        # Expand grouped band conditions into individual bands.
        raw_bands = data.get("bands", {})
        for group_name, individual_bands in _BAND_GROUP_MAP.items():
            group_data = raw_bands.get(group_name, {})
            day_cond = group_data.get("day", "")
            night_cond = group_data.get("night", "")
            for band in individual_bands:
                conditions.bands[band] = BandCondition(
                    band=band, day=day_cond, night=night_cond,
                )

        # VHF conditions.
        for v in data.get("vhf", []):
            conditions.vhf.append(VHFCondition(
                name=v.get("name", ""),
                location=v.get("location", ""),
                status=v.get("status", ""),
            ))

        # Forecast data.
        conditions.forecast = PropagationForecast(
            source="hamqsl",
            geomag_field=data.get("geomag_field", ""),
            signal_noise=data.get("signal_noise", ""),
            muf=data.get("muf", ""),
            updated=data.get("updated", ""),
        )

    def _apply_k_index(self, conditions: PropagationConditions, data: dict) -> None:
        """Apply NOAA K-index data (overrides HamQSL if newer)."""
        kp = self._safe_float(data.get("kp"))
        if kp is not None:
            conditions.solar.k_index = kp

        a_running = self._safe_int(data.get("a_running"))
        if a_running is not None:
            conditions.solar.a_index = a_running

    def _apply_solar_cycle(self, conditions: PropagationConditions, data: dict) -> None:
        """Apply monthly solar cycle data."""
        ssn = data.get("ssn")
        if ssn is not None and ssn != -1.0:
            # Only override if HamQSL didn't provide a value.
            if conditions.solar.sunspot_number is None:
                conditions.solar.sunspot_number = int(ssn)

        f10_7 = data.get("f10_7")
        if f10_7 is not None and f10_7 != -1.0:
            if conditions.solar.solar_flux is None:
                conditions.solar.solar_flux = float(f10_7)

        # Add trend info to forecast.
        smoothed = data.get("smoothed_ssn")
        if ssn is not None and smoothed is not None and smoothed != -1.0:
            if ssn > smoothed:
                conditions.forecast.solar_flux_trend = "above average"
            elif ssn < smoothed:
                conditions.forecast.solar_flux_trend = "below average"
            else:
                conditions.forecast.solar_flux_trend = "average"

    # -- Storm level from K-index -------------------------------------------

    @staticmethod
    def _k_to_storm(k: float) -> str:
        """Convert K-index to NOAA G-scale storm level."""
        if k >= 9:
            return "G5 - Extreme"
        elif k >= 8:
            return "G4 - Severe"
        elif k >= 7:
            return "G3 - Strong"
        elif k >= 6:
            return "G2 - Moderate"
        elif k >= 5:
            return "G1 - Minor"
        else:
            return "None"

    # -- Persistence and MQTT -----------------------------------------------

    async def _persist_and_publish(
        self,
        conditions: PropagationConditions,
        prev: PropagationConditions | None,
    ) -> None:
        """Store snapshot in DB and publish to MQTT."""
        solar = conditions.solar
        band_dict = {name: asdict(bc) for name, bc in conditions.bands.items()}

        # Persist to database.
        try:
            raw = {
                "source_status": conditions.source_status,
                "vhf": [asdict(v) for v in conditions.vhf],
                "drap": conditions.drap,
                "forecast": asdict(conditions.forecast),
            }
            await db.execute(
                """
                INSERT INTO elmer.propagation_data
                    (solar_flux, sunspot_number, a_index, k_index,
                     x_ray_flux, geomag_storm, band_conditions, raw_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                """,
                solar.solar_flux,
                solar.sunspot_number,
                solar.a_index,
                solar.k_index,
                solar.x_ray_flux,
                solar.geomag_storm,
                json.dumps(band_dict),
                json.dumps(raw, default=str),
            )
        except Exception:
            logger.warning("Failed to persist propagation data", exc_info=True)

        # Publish current conditions to MQTT.
        try:
            summary = {
                "solar_flux": solar.solar_flux,
                "sunspot_number": solar.sunspot_number,
                "a_index": solar.a_index,
                "k_index": solar.k_index,
                "x_ray_flux": solar.x_ray_flux,
                "geomag_storm": solar.geomag_storm,
                "geomag_field": solar.geomag_field,
                "bands": band_dict,
                "updated": conditions.updated,
            }
            await mqtt_publish(
                "elmer/propagation/conditions",
                json.dumps(summary, default=str),
            )
        except Exception:
            logger.debug("Failed to publish propagation conditions")

        # Check for alert conditions.
        await self._check_alerts(conditions, prev)

    async def _check_alerts(
        self,
        current: PropagationConditions,
        prev: PropagationConditions | None,
    ) -> None:
        """Publish alerts when conditions change significantly."""
        alerts: list[dict[str, Any]] = []
        solar = current.solar

        # K-index storm warning (K >= 4).
        if solar.k_index is not None and solar.k_index >= 4:
            prev_k = prev.solar.k_index if prev else None
            if prev_k is None or prev_k < 4:
                alerts.append({
                    "type": "k_index_elevated",
                    "message": f"K-index rose to {solar.k_index:.1f} (storm threshold)",
                    "k_index": solar.k_index,
                    "geomag_storm": solar.geomag_storm,
                })

        # Solar flare detection (M-class or X-class).
        if solar.x_ray_flux:
            xray = solar.x_ray_flux.upper()
            if xray.startswith("M") or xray.startswith("X"):
                prev_xray = (prev.solar.x_ray_flux or "").upper() if prev else ""
                if not prev_xray.startswith("M") and not prev_xray.startswith("X"):
                    alerts.append({
                        "type": "solar_flare",
                        "message": f"Solar flare detected: {solar.x_ray_flux}",
                        "x_ray_class": solar.x_ray_flux,
                    })

        # Band opening detection (poor -> good).
        if prev:
            for band_name, bc in current.bands.items():
                prev_bc = prev.bands.get(band_name)
                if prev_bc is None:
                    continue
                for period in ("day", "night"):
                    old_cond = getattr(prev_bc, period, "").lower()
                    new_cond = getattr(bc, period, "").lower()
                    if old_cond == "poor" and new_cond == "good":
                        alerts.append({
                            "type": "band_opening",
                            "message": f"{band_name} opened ({period}): Poor -> Good",
                            "band": band_name,
                            "period": period,
                        })

        # Publish alerts.
        for alert in alerts:
            alert["timestamp"] = datetime.now(timezone.utc).isoformat()
            try:
                await mqtt_publish(
                    "elmer/propagation/alert",
                    json.dumps(alert, default=str),
                )
                logger.info("Propagation alert: %s", alert["message"])
            except Exception:
                logger.debug("Failed to publish propagation alert")

    # -- Helpers ------------------------------------------------------------

    @staticmethod
    def _safe_float(val: Any) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(val: Any) -> int | None:
        if val is None or val == "":
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: PropagationService | None = None


def get_service() -> PropagationService:
    """Return the shared PropagationService instance."""
    global _service
    if _service is None:
        _service = PropagationService()
    return _service

"""POTA (Parks on the Air) service — park lookup, spots, activation planning.

Fetches from the POTA API (https://api.pota.app/):
  - Park details and activation stats
  - Current activator spots
  - Parks by location (state/province)

Combines with Elmer's propagation service for band recommendations
and activation planning.

Caches aggressively to respect the POTA API:
  - Spots: 2 minutes
  - Park details: 1 hour
  - Location park lists: 24 hours
"""

import asyncio
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger("elmer.pota")

_USER_AGENT = "Elmer/0.1 (amateur-radio-home-lab)"
_FETCH_TIMEOUT = 15.0
_POTA_BASE = "https://api.pota.app"

# Cache TTLs (seconds).
_TTL_SPOTS = 120        # 2 minutes
_TTL_PARK = 3600        # 1 hour
_TTL_LOCATION = 86400   # 24 hours


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ParkInfo:
    reference: str = ""
    name: str = ""
    grid4: str = ""
    grid6: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    location_desc: str = ""
    location_name: str = ""
    park_type: str = ""
    active: bool = True
    activations: int = 0
    attempts: int = 0
    contacts: int = 0
    first_activator: str = ""
    first_activation_date: str = ""
    website: str = ""
    access_methods: str = ""
    distance_miles: float | None = None


@dataclass
class POTASpot:
    spot_id: int = 0
    activator: str = ""
    frequency: str = ""
    mode: str = ""
    reference: str = ""
    park_name: str = ""
    location_desc: str = ""
    spotter: str = ""
    source: str = ""
    comments: str = ""
    spot_time: str = ""


@dataclass
class BandRecommendation:
    band: str = ""
    mode: str = ""
    time_window: str = ""
    condition: str = ""
    rationale: str = ""


@dataclass
class ActivationPlan:
    park: ParkInfo = field(default_factory=ParkInfo)
    distance_miles: float = 0.0
    bearing: float = 0.0
    band_recommendations: list[BandRecommendation] = field(default_factory=list)
    nearby_parks: list[ParkInfo] = field(default_factory=list)
    current_spots_at_park: list[POTASpot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

def _grid_to_latlon(grid: str) -> tuple[float, float]:
    """Convert Maidenhead grid locator to approximate lat/lon center."""
    grid = grid.strip().upper()
    if len(grid) < 4:
        return (0.0, 0.0)

    lon = (ord(grid[0]) - ord("A")) * 20 - 180
    lat = (ord(grid[1]) - ord("A")) * 10 - 90
    lon += int(grid[2]) * 2
    lat += int(grid[3]) * 1

    if len(grid) >= 6:
        lon += (ord(grid[4]) - ord("A")) * (2 / 24)
        lat += (ord(grid[5]) - ord("A")) * (1 / 24)
        lon += 1 / 24
        lat += 0.5 / 24
    else:
        lon += 1
        lat += 0.5

    return (lat, lon)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in miles between two lat/lon points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees from point 1 to point 2."""
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2)
    y = (math.cos(lat1) * math.sin(lat2) -
         math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ---------------------------------------------------------------------------
# POTA Service
# ---------------------------------------------------------------------------

class POTAService:
    """Fetches, caches, and analyzes POTA data."""

    def __init__(self) -> None:
        self._spots_cache: list[POTASpot] | None = None
        self._spots_cache_time: float = 0.0

        self._park_cache: dict[str, tuple[ParkInfo, float]] = {}
        self._location_cache: dict[str, tuple[list[ParkInfo], float]] = {}

        self._lock = asyncio.Lock()

    # -- Public API ---------------------------------------------------------

    async def get_park(self, ref: str) -> ParkInfo | None:
        """Fetch park details + stats (cached 1 hour)."""
        ref = ref.upper()
        cached = self._park_cache.get(ref)
        if cached and (time.monotonic() - cached[1]) < _TTL_PARK:
            return cached[0]

        park_data, stats_data = await asyncio.gather(
            self._fetch_json(f"/park/{ref}"),
            self._fetch_json(f"/park/stats/{ref}"),
            return_exceptions=True,
        )

        if isinstance(park_data, Exception) or not park_data:
            return None

        park = self._parse_park(park_data)

        if isinstance(stats_data, dict):
            park.activations = stats_data.get("activations", 0)
            park.attempts = stats_data.get("attempts", 0)
            park.contacts = stats_data.get("contacts", 0)

        self._park_cache[ref] = (park, time.monotonic())
        return park

    async def search_parks(
        self,
        state: str | None = None,
        name: str | None = None,
    ) -> list[ParkInfo]:
        """Search parks by state/location and optional name filter."""
        loc = state or settings.POTA_HOME_STATE
        parks = await self._get_location_parks(loc)

        if name:
            name_lower = name.lower()
            parks = [p for p in parks if name_lower in p.name.lower()]

        return parks

    async def get_current_spots(self) -> list[POTASpot]:
        """Fetch current POTA activator spots (cached 2 min)."""
        if (self._spots_cache is not None and
                (time.monotonic() - self._spots_cache_time) < _TTL_SPOTS):
            return self._spots_cache

        data = await self._fetch_json("/spot")
        if not isinstance(data, list):
            return self._spots_cache or []

        spots = []
        for s in data:
            spots.append(POTASpot(
                spot_id=s.get("spotId", 0),
                activator=s.get("activator", ""),
                frequency=s.get("frequency", ""),
                mode=s.get("mode", ""),
                reference=s.get("reference", ""),
                park_name=s.get("name", ""),
                location_desc=s.get("locationDesc", ""),
                spotter=s.get("spotter", ""),
                source=s.get("source", ""),
                comments=s.get("comments", ""),
                spot_time=s.get("spotTime", ""),
            ))

        self._spots_cache = spots
        self._spots_cache_time = time.monotonic()
        return spots

    async def get_nearby_parks(
        self,
        grid: str | None = None,
        radius_miles: float = 50.0,
    ) -> list[ParkInfo]:
        """Parks within radius of a grid square (default: home grid)."""
        grid = grid or settings.POTA_HOME_GRID
        home_lat, home_lon = _grid_to_latlon(grid)

        parks = await self._get_location_parks(settings.POTA_HOME_STATE)

        nearby = []
        for p in parks:
            if p.latitude == 0.0 and p.longitude == 0.0:
                continue
            dist = _haversine(home_lat, home_lon, p.latitude, p.longitude)
            if dist <= radius_miles:
                p.distance_miles = round(dist, 1)
                nearby.append(p)

        nearby.sort(key=lambda p: p.distance_miles or 999)
        return nearby

    async def plan_activation(self, ref: str) -> ActivationPlan:
        """Comprehensive activation plan for a park."""
        park = await self.get_park(ref)
        if park is None:
            raise ValueError(f"Park {ref} not found")

        home_lat, home_lon = _grid_to_latlon(settings.POTA_HOME_GRID)

        dist = _haversine(home_lat, home_lon, park.latitude, park.longitude)
        brng = _bearing(home_lat, home_lon, park.latitude, park.longitude)

        # Get band recommendations, nearby parks, and spots concurrently.
        band_recs, nearby, spots = await asyncio.gather(
            self._build_band_recommendations(),
            self.get_nearby_parks(
                grid=park.grid4 or settings.POTA_HOME_GRID,
                radius_miles=30.0,
            ),
            self.get_current_spots(),
            return_exceptions=True,
        )

        if isinstance(band_recs, Exception):
            band_recs = []
        if isinstance(nearby, Exception):
            nearby = []
        if isinstance(spots, Exception):
            spots = []

        # Filter nearby parks to exclude the target park.
        nearby = [p for p in nearby if p.reference != ref][:10]

        # Find spots at this park.
        park_spots = [s for s in spots if s.reference == ref]

        # Build notes.
        notes = []
        if park.activations > 0:
            notes.append(
                f"Previously activated {park.activations} times "
                f"({park.contacts} total contacts)"
            )
        if park.first_activator:
            notes.append(
                f"First activated by {park.first_activator} "
                f"on {park.first_activation_date}"
            )
        if park.access_methods:
            notes.append(f"Access: {park.access_methods}")
        if nearby:
            notes.append(
                f"{len(nearby)} other parks within 30 miles for multi-park activation"
            )

        return ActivationPlan(
            park=park,
            distance_miles=round(dist, 1),
            bearing=round(brng, 0),
            band_recommendations=band_recs,
            nearby_parks=nearby,
            current_spots_at_park=park_spots,
            notes=notes,
        )

    # -- Private fetchers ---------------------------------------------------

    async def _fetch_json(self, path: str) -> Any:
        """GET from the POTA API with caching-friendly headers."""
        url = f"{_POTA_BASE}{path}"
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("POTA API %s returned %s", path, exc.response.status_code)
            return None
        except (httpx.RequestError, Exception) as exc:
            logger.warning("POTA API %s failed: %s", path, exc)
            return None

    async def _get_location_parks(self, location: str) -> list[ParkInfo]:
        """Fetch parks for a location (e.g. US-CO), cached 24h."""
        cached = self._location_cache.get(location)
        if cached and (time.monotonic() - cached[1]) < _TTL_LOCATION:
            return cached[0]

        data = await self._fetch_json(f"/location/parks/{location}")
        if not isinstance(data, list):
            return cached[0] if cached else []

        parks = [self._parse_park(p) for p in data]
        self._location_cache[location] = (parks, time.monotonic())
        logger.info("Cached %d parks for location %s", len(parks), location)
        return parks

    def _parse_park(self, data: dict) -> ParkInfo:
        """Parse a POTA API park object into ParkInfo."""
        return ParkInfo(
            reference=data.get("reference", ""),
            name=data.get("name", ""),
            grid4=data.get("grid4", ""),
            grid6=data.get("grid6", ""),
            latitude=float(data.get("latitude", 0) or 0),
            longitude=float(data.get("longitude", 0) or 0),
            location_desc=data.get("locationDesc", ""),
            location_name=data.get("locationName", ""),
            park_type=data.get("parktypeDesc", ""),
            active=bool(data.get("active", 1)),
            activations=data.get("activations", 0) or 0,
            attempts=data.get("attempts", 0) or 0,
            contacts=data.get("contacts", 0) or 0,
            first_activator=data.get("firstActivator", "") or "",
            first_activation_date=data.get("firstActivationDate", "") or "",
            website=data.get("website", "") or "",
            access_methods=data.get("accessMethods", "") or "",
        )

    async def _build_band_recommendations(self) -> list[BandRecommendation]:
        """Build band recommendations from propagation data."""
        from .propagation import get_service as get_prop_service

        try:
            prop = get_prop_service()
            conditions = await prop.get_current_conditions()
        except Exception:
            logger.warning("Could not get propagation data for band recommendations")
            return [
                BandRecommendation(
                    band="20m", mode="SSB",
                    time_window="Daytime",
                    condition="Unknown",
                    rationale="Default POTA band — good for daytime activations",
                ),
                BandRecommendation(
                    band="40m", mode="SSB",
                    time_window="Late afternoon / evening",
                    condition="Unknown",
                    rationale="Reliable for regional contacts",
                ),
            ]

        recs = []
        now_utc = datetime.now(timezone.utc).hour

        # Band priority for POTA based on time of day.
        if 12 <= now_utc <= 23:  # Daytime in CO (UTC 12-23 ≈ 5am-4pm MT)
            band_priority = ["20m", "17m", "15m", "40m", "10m"]
        elif 0 <= now_utc < 4:   # Evening in CO
            band_priority = ["40m", "80m", "20m", "60m"]
        else:                     # Early morning
            band_priority = ["40m", "20m", "80m", "17m"]

        for band_name in band_priority:
            bc = conditions.bands.get(band_name)
            if not bc:
                continue

            # Determine current condition based on time of day.
            if 12 <= now_utc <= 23:
                cond = bc.day
                time_label = "Daytime"
            else:
                cond = bc.night
                time_label = "Night"

            if cond in ("Good", "Fair"):
                # Recommend SSB for POTA primary, CW as secondary.
                recs.append(BandRecommendation(
                    band=band_name,
                    mode="SSB",
                    time_window=time_label,
                    condition=cond,
                    rationale=f"{band_name} conditions are {cond} for {time_label.lower()} — "
                              f"good choice for POTA activation",
                ))

        # Always include 20m and 40m as fallbacks if not already present.
        included = {r.band for r in recs}
        if "20m" not in included:
            recs.append(BandRecommendation(
                band="20m", mode="SSB",
                time_window="Daytime",
                condition="Fair",
                rationale="20m is the most popular POTA band — always worth trying",
            ))
        if "40m" not in included:
            recs.append(BandRecommendation(
                band="40m", mode="SSB",
                time_window="Late afternoon",
                condition="Fair",
                rationale="40m reliable for regional contacts, especially later in the day",
            ))

        return recs


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_service: POTAService | None = None


def get_service() -> POTAService:
    global _service
    if _service is None:
        _service = POTAService()
    return _service

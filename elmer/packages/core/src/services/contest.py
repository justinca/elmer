"""Contest service — calendar, live dashboard, and band recommendations.

Data sources:
  - Hardcoded major contest calendar (~20 contests with rules/exchange)
  - WA7BNM Contest Calendar (supplementary, weekly scrape)
  - Log4OM QSO data via worker proxy (for live contest analysis)
  - Propagation service (for band recommendations)
"""

import asyncio
import calendar
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger("elmer.contest")

_USER_AGENT = "Elmer/0.1 (amateur-radio-home-lab)"
_FETCH_TIMEOUT = 15.0
_WA7BNM_URL = "https://www.contestcalendar.com/contestcal.php"

# Cache TTLs.
_TTL_CALENDAR = 604800   # 7 days
_TTL_DASHBOARD = 30      # 30 seconds for live contest data


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ContestInfo:
    name: str = ""
    full_name: str = ""
    start_utc: str = ""
    end_utc: str = ""
    mode: str = ""
    bands: list[str] = field(default_factory=list)
    exchange: str = ""
    rules_url: str = ""
    sponsor: str = ""
    recurring: str = ""
    is_major: bool = False
    source: str = "hardcoded"


@dataclass
class ContestQSORate:
    period_minutes: int = 0
    qso_count: int = 0
    rate_per_hour: float = 0.0


@dataclass
class ContestDashboard:
    contest_name: str = ""
    total_qsos: int = 0
    unique_calls: int = 0
    unique_countries: int = 0
    bands_worked: dict[str, int] = field(default_factory=dict)
    modes_worked: dict[str, int] = field(default_factory=dict)
    rate_last_10: ContestQSORate = field(default_factory=ContestQSORate)
    rate_last_60: ContestQSORate = field(default_factory=ContestQSORate)
    first_qso: str = ""
    last_qso: str = ""
    elapsed_hours: float = 0.0
    multipliers: int = 0
    estimated_score: int = 0


@dataclass
class BandRecommendation:
    suggested_band: str = ""
    current_band: str = ""
    reason: str = ""
    band_condition: str = ""
    time_on_current: str = ""


# ---------------------------------------------------------------------------
# Hardcoded major contests
# ---------------------------------------------------------------------------

_HF_BANDS = ["160m", "80m", "40m", "20m", "15m", "10m"]

_MAJOR_CONTESTS: list[dict[str, Any]] = [
    {
        "name": "NAQP-CW",
        "full_name": "North American QSO Party (CW)",
        "mode": "CW", "exchange": "Name + State/Province",
        "recurring": "2nd Saturday of January",
        "bands": _HF_BANDS, "sponsor": "NCJ", "is_major": True,
    },
    {
        "name": "NAQP-SSB",
        "full_name": "North American QSO Party (SSB)",
        "mode": "SSB", "exchange": "Name + State/Province",
        "recurring": "3rd Saturday of January",
        "bands": _HF_BANDS, "sponsor": "NCJ", "is_major": True,
    },
    {
        "name": "CQWW-160-CW",
        "full_name": "CQ 160-Meter Contest (CW)",
        "mode": "CW", "exchange": "RST + State/Province/Country",
        "recurring": "Last full weekend of January",
        "bands": ["160m"], "sponsor": "CQ Magazine", "is_major": True,
    },
    {
        "name": "ARRL-DX-CW",
        "full_name": "ARRL DX Contest (CW)",
        "mode": "CW", "exchange": "RST + State/Province (W/VE) or Power (DX)",
        "recurring": "3rd full weekend of February",
        "bands": _HF_BANDS, "sponsor": "ARRL", "is_major": True,
    },
    {
        "name": "CQWW-160-SSB",
        "full_name": "CQ 160-Meter Contest (SSB)",
        "mode": "SSB", "exchange": "RST + State/Province/Country",
        "recurring": "Last full weekend of February",
        "bands": ["160m"], "sponsor": "CQ Magazine", "is_major": True,
    },
    {
        "name": "ARRL-DX-SSB",
        "full_name": "ARRL DX Contest (SSB)",
        "mode": "SSB", "exchange": "RST + State/Province (W/VE) or Power (DX)",
        "recurring": "1st full weekend of March",
        "bands": _HF_BANDS, "sponsor": "ARRL", "is_major": True,
    },
    {
        "name": "CQ-WPX-SSB",
        "full_name": "CQ WPX Contest (SSB)",
        "mode": "SSB", "exchange": "RST + Serial",
        "recurring": "Last full weekend of March",
        "bands": _HF_BANDS, "sponsor": "CQ Magazine", "is_major": True,
    },
    {
        "name": "CQ-WPX-CW",
        "full_name": "CQ WPX Contest (CW)",
        "mode": "CW", "exchange": "RST + Serial",
        "recurring": "Last full weekend of May",
        "bands": _HF_BANDS, "sponsor": "CQ Magazine", "is_major": True,
    },
    {
        "name": "ARRL-FD",
        "full_name": "ARRL Field Day",
        "mode": "Mixed", "exchange": "Category + ARRL Section",
        "recurring": "4th full weekend of June",
        "bands": _HF_BANDS + ["6m", "2m"], "sponsor": "ARRL", "is_major": True,
    },
    {
        "name": "IARU-HF",
        "full_name": "IARU HF World Championship",
        "mode": "Mixed", "exchange": "RST + ITU Zone (or HQ abbreviation)",
        "recurring": "2nd full weekend of July",
        "bands": _HF_BANDS, "sponsor": "IARU", "is_major": True,
    },
    {
        "name": "STATE-QSO-CO",
        "full_name": "Colorado QSO Party",
        "mode": "Mixed", "exchange": "RST + County (CO) or State (non-CO)",
        "recurring": "Last full weekend of August",
        "bands": _HF_BANDS, "sponsor": "Pikes Peak Radio Amateur Assoc.", "is_major": False,
    },
    {
        "name": "CQ-WW-RTTY",
        "full_name": "CQ WW RTTY DX Contest",
        "mode": "RTTY", "exchange": "RST + CQ Zone",
        "recurring": "Last full weekend of September",
        "bands": ["80m", "40m", "20m", "15m", "10m"], "sponsor": "CQ Magazine", "is_major": True,
    },
    {
        "name": "CQ-WW-SSB",
        "full_name": "CQ World Wide DX Contest (SSB)",
        "mode": "SSB", "exchange": "RST + CQ Zone",
        "recurring": "Last full weekend of October",
        "bands": _HF_BANDS, "sponsor": "CQ Magazine", "is_major": True,
    },
    {
        "name": "ARRL-SS-CW",
        "full_name": "ARRL Sweepstakes (CW)",
        "mode": "CW", "exchange": "Serial + Precedence + Call + Check + Section",
        "recurring": "1st full weekend of November",
        "bands": _HF_BANDS, "sponsor": "ARRL", "is_major": True,
    },
    {
        "name": "ARRL-SS-SSB",
        "full_name": "ARRL Sweepstakes (SSB)",
        "mode": "SSB", "exchange": "Serial + Precedence + Call + Check + Section",
        "recurring": "3rd full weekend of November",
        "bands": _HF_BANDS, "sponsor": "ARRL", "is_major": True,
    },
    {
        "name": "CQ-WW-CW",
        "full_name": "CQ World Wide DX Contest (CW)",
        "mode": "CW", "exchange": "RST + CQ Zone",
        "recurring": "Last full weekend of November",
        "bands": _HF_BANDS, "sponsor": "CQ Magazine", "is_major": True,
    },
    {
        "name": "ARRL-160",
        "full_name": "ARRL 160-Meter Contest",
        "mode": "CW", "exchange": "RST + ARRL Section",
        "recurring": "1st full weekend of December",
        "bands": ["160m"], "sponsor": "ARRL", "is_major": True,
    },
    {
        "name": "ARRL-10",
        "full_name": "ARRL 10-Meter Contest",
        "mode": "Mixed", "exchange": "RST + State/Province (W/VE) or Serial (DX)",
        "recurring": "2nd full weekend of December",
        "bands": ["10m"], "sponsor": "ARRL", "is_major": True,
    },
]


# ---------------------------------------------------------------------------
# Date computation
# ---------------------------------------------------------------------------

def _find_nth_weekday_weekend(year: int, month: int, n: int) -> date:
    """Find the Saturday of the Nth full weekend of a month.

    A 'full weekend' is a Saturday-Sunday pair entirely within the month.
    """
    cal = calendar.monthcalendar(year, month)
    weekends_found = 0
    for week in cal:
        sat = week[5]  # Saturday
        sun = week[6]  # Sunday
        if sat != 0 and sun != 0:
            weekends_found += 1
            if weekends_found == n:
                return date(year, month, sat)
    # Fallback: return last found.
    return date(year, month, sat)


def _find_last_full_weekend(year: int, month: int) -> date:
    """Find the Saturday of the last full weekend of a month."""
    cal = calendar.monthcalendar(year, month)
    for week in reversed(cal):
        sat = week[5]
        sun = week[6]
        if sat != 0 and sun != 0:
            return date(year, month, sat)
    return date(year, month, 1)


def _find_nth_day(year: int, month: int, n: int, weekday: int = 5) -> date:
    """Find the Nth occurrence of a weekday (0=Mon, 5=Sat) in a month."""
    cal = calendar.monthcalendar(year, month)
    count = 0
    for week in cal:
        if week[weekday] != 0:
            count += 1
            if count == n:
                return date(year, month, week[weekday])
    return date(year, month, week[weekday])


def _compute_contest_dates(recurring: str, year: int) -> tuple[str, str] | None:
    """Parse recurring description into (start_utc, end_utc) ISO strings."""
    r = recurring.lower().strip()

    ordinals = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5}
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    # Pattern: "Nth full weekend of Month"
    m = re.match(r"(\w+)\s+full\s+weekend\s+of\s+(\w+)", r)
    if m:
        ord_str, month_str = m.groups()
        n = ordinals.get(ord_str, 0)
        month = months.get(month_str, 0)
        if n and month:
            sat = _find_nth_weekday_weekend(year, month, n)
            sun = sat + timedelta(days=1)
            return (
                f"{sat.isoformat()}T00:00:00Z",
                f"{sun.isoformat()}T23:59:59Z",
            )

    # Pattern: "Last full weekend of Month"
    m = re.match(r"last\s+full\s+weekend\s+of\s+(\w+)", r)
    if m:
        month_str = m.group(1)
        month = months.get(month_str, 0)
        if month:
            sat = _find_last_full_weekend(year, month)
            sun = sat + timedelta(days=1)
            return (
                f"{sat.isoformat()}T00:00:00Z",
                f"{sun.isoformat()}T23:59:59Z",
            )

    # Pattern: "Nth Saturday of Month"
    m = re.match(r"(\w+)\s+saturday\s+of\s+(\w+)", r)
    if m:
        ord_str, month_str = m.groups()
        n = ordinals.get(ord_str, 0)
        month = months.get(month_str, 0)
        if n and month:
            sat = _find_nth_day(year, month, n, weekday=5)
            return (
                f"{sat.isoformat()}T18:00:00Z",
                f"{(sat + timedelta(days=1)).isoformat()}T05:59:59Z",
            )

    # Pattern: "Last Saturday of Month"
    m = re.match(r"last\s+saturday\s+of\s+(\w+)", r)
    if m:
        month_str = m.group(1)
        month = months.get(month_str, 0)
        if month:
            sat = _find_last_full_weekend(year, month)
            return (
                f"{sat.isoformat()}T00:00:00Z",
                f"{(sat + timedelta(days=1)).isoformat()}T23:59:59Z",
            )

    return None


# ---------------------------------------------------------------------------
# Contest Service
# ---------------------------------------------------------------------------

class ContestService:
    """Contest calendar, live monitoring, and band recommendations."""

    def __init__(self) -> None:
        self._calendar_cache: list[ContestInfo] | None = None
        self._calendar_cache_time: float = 0.0
        self._wa7bnm_cache: list[ContestInfo] | None = None
        self._wa7bnm_cache_time: float = 0.0
        self._lock = asyncio.Lock()

    # -- Public API ---------------------------------------------------------

    async def get_upcoming_contests(self, days: int = 30) -> list[ContestInfo]:
        """Contests happening in the next N days."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        year = now.year

        contests: list[ContestInfo] = []

        # Compute dates for hardcoded contests (this year and next).
        for contest_dict in _MAJOR_CONTESTS:
            for y in (year, year + 1):
                dates = _compute_contest_dates(contest_dict["recurring"], y)
                if not dates:
                    continue

                start_str, end_str = dates
                try:
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                except ValueError:
                    continue

                if start_dt > cutoff or end_dt < now:
                    continue

                contests.append(ContestInfo(
                    name=contest_dict["name"],
                    full_name=contest_dict["full_name"],
                    start_utc=start_str,
                    end_utc=end_str,
                    mode=contest_dict["mode"],
                    bands=list(contest_dict.get("bands", [])),
                    exchange=contest_dict.get("exchange", ""),
                    sponsor=contest_dict.get("sponsor", ""),
                    recurring=contest_dict["recurring"],
                    is_major=contest_dict.get("is_major", False),
                    source="hardcoded",
                ))

        # Merge WA7BNM data (supplementary).
        wa7bnm = await self._get_wa7bnm_contests()
        for c in wa7bnm:
            try:
                start_dt = datetime.fromisoformat(c.start_utc.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(c.end_utc.replace("Z", "+00:00"))
            except ValueError:
                continue
            if start_dt > cutoff or end_dt < now:
                continue
            # Avoid duplicates by name.
            if not any(existing.name == c.name for existing in contests):
                contests.append(c)

        contests.sort(key=lambda c: c.start_utc)
        return contests

    async def get_contest_info(self, name: str) -> ContestInfo | None:
        """Lookup a specific contest by name slug."""
        name_upper = name.upper()
        for contest_dict in _MAJOR_CONTESTS:
            if contest_dict["name"].upper() == name_upper:
                year = datetime.now(timezone.utc).year
                dates = _compute_contest_dates(contest_dict["recurring"], year)
                start_str, end_str = dates if dates else ("", "")
                return ContestInfo(
                    name=contest_dict["name"],
                    full_name=contest_dict["full_name"],
                    start_utc=start_str,
                    end_utc=end_str,
                    mode=contest_dict["mode"],
                    bands=list(contest_dict.get("bands", [])),
                    exchange=contest_dict.get("exchange", ""),
                    sponsor=contest_dict.get("sponsor", ""),
                    recurring=contest_dict["recurring"],
                    is_major=contest_dict.get("is_major", False),
                    source="hardcoded",
                )
        return None

    async def analyze_live_contest(self, contest_name: str) -> ContestDashboard:
        """Build live contest dashboard from Log4OM data."""
        # Fetch recent QSOs from worker (last 3 days to cover any contest).
        since = (date.today() - timedelta(days=3)).isoformat()
        qsos = await self._fetch_contest_qsos(since)

        # Filter by contest name (case-insensitive substring match).
        name_lower = contest_name.lower().replace("-", "").replace("_", "")
        contest_qsos = []
        for q in qsos:
            contest_field = (q.get("contest", "") or "").lower().replace("-", "").replace("_", "")
            if name_lower in contest_field or contest_field in name_lower:
                contest_qsos.append(q)

        if not contest_qsos:
            return ContestDashboard(contest_name=contest_name)

        # Calculate metrics.
        calls = set()
        countries = set()
        bands: dict[str, int] = {}
        modes: dict[str, int] = {}
        timestamps: list[datetime] = []

        for q in contest_qsos:
            call = q.get("call", "")
            if call:
                calls.add(call)
            country = q.get("country", "")
            if country:
                countries.add(country)

            band = q.get("band", "")
            if band:
                bands[band] = bands.get(band, 0) + 1

            mode = q.get("mode", "")
            if mode:
                modes[mode] = modes.get(mode, 0) + 1

            qso_date = q.get("qso_date", "")
            if qso_date:
                try:
                    ts = datetime.fromisoformat(qso_date.replace("Z", "+00:00"))
                    timestamps.append(ts)
                except ValueError:
                    pass

        # Calculate rates.
        now = datetime.now(timezone.utc)
        rate_10 = self._calculate_rate(timestamps, now, 10)
        rate_60 = self._calculate_rate(timestamps, now, 60)

        # Elapsed time.
        if timestamps:
            first = min(timestamps)
            last = max(timestamps)
            elapsed = (last - first).total_seconds() / 3600
        else:
            first = now
            last = now
            elapsed = 0

        # Multipliers (unique countries as default).
        mults = len(countries)

        # Score estimate (1 point per QSO * multipliers as simple estimate).
        score = len(contest_qsos) * mults

        return ContestDashboard(
            contest_name=contest_name,
            total_qsos=len(contest_qsos),
            unique_calls=len(calls),
            unique_countries=len(countries),
            bands_worked=bands,
            modes_worked=modes,
            rate_last_10=rate_10,
            rate_last_60=rate_60,
            first_qso=first.isoformat() if timestamps else "",
            last_qso=last.isoformat() if timestamps else "",
            elapsed_hours=round(elapsed, 2),
            multipliers=mults,
            estimated_score=score,
        )

    async def recommend_band_change(
        self,
        current_band: str,
        contest_name: str | None = None,
    ) -> BandRecommendation:
        """Suggest optimal band based on propagation and contest state."""
        from .propagation import get_service as get_prop_service

        try:
            prop = get_prop_service()
            conditions = await prop.get_current_conditions()
        except Exception:
            return BandRecommendation(
                suggested_band=current_band,
                current_band=current_band,
                reason="Could not fetch propagation data — staying on current band",
            )

        now_utc = datetime.now(timezone.utc).hour

        # Score each band based on conditions.
        band_scores: list[tuple[str, float, str]] = []
        for band_name in ["10m", "12m", "15m", "17m", "20m", "40m", "80m", "160m"]:
            bc = conditions.bands.get(band_name)
            if not bc:
                continue

            cond = bc.day if 12 <= now_utc <= 23 else bc.night
            score = {"Good": 3, "Fair": 2, "Poor": 1}.get(cond, 0)

            # Boost high bands during daytime, low bands at night.
            if 12 <= now_utc <= 23:
                if band_name in ("10m", "12m", "15m", "17m", "20m"):
                    score += 1
            else:
                if band_name in ("40m", "80m", "160m"):
                    score += 1

            # Penalize current band slightly to encourage trying something new.
            if band_name == current_band:
                score -= 0.5

            band_scores.append((band_name, score, cond))

        band_scores.sort(key=lambda x: x[1], reverse=True)

        if not band_scores:
            return BandRecommendation(
                suggested_band=current_band,
                current_band=current_band,
                reason="No band condition data available",
            )

        best_band, best_score, best_cond = band_scores[0]

        if best_band == current_band:
            reason = f"Stay on {current_band} — conditions are {best_cond} and it's your best option"
        else:
            reason = (
                f"Consider moving to {best_band} — conditions are {best_cond} "
                f"(better than {current_band} right now)"
            )

        return BandRecommendation(
            suggested_band=best_band,
            current_band=current_band,
            reason=reason,
            band_condition=best_cond,
        )

    async def get_contest_history(self) -> list[dict[str, Any]]:
        """Return historical contest participation from Log4OM."""
        url = f"{settings.worker_base_url}/log4om/contests"
        try:
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch contest history: %s", exc)
            return []

    # -- Private methods ----------------------------------------------------

    async def _fetch_contest_qsos(self, since: str) -> list[dict]:
        """Fetch recent QSOs from the worker."""
        url = f"{settings.worker_base_url}/log4om/qsos"
        try:
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
                resp = await client.get(url, params={"since": since, "limit": 500})
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, list) else data.get("qsos", [])
        except Exception as exc:
            logger.warning("Failed to fetch contest QSOs: %s", exc)
            return []

    def _calculate_rate(
        self,
        timestamps: list[datetime],
        now: datetime,
        minutes: int,
    ) -> ContestQSORate:
        """Calculate QSO rate for the last N minutes."""
        cutoff = now - timedelta(minutes=minutes)
        count = sum(1 for ts in timestamps if ts >= cutoff)
        rate = (count / minutes) * 60 if minutes > 0 else 0
        return ContestQSORate(
            period_minutes=minutes,
            qso_count=count,
            rate_per_hour=round(rate, 1),
        )

    async def _get_wa7bnm_contests(self) -> list[ContestInfo]:
        """Fetch WA7BNM contest calendar (cached weekly)."""
        if (self._wa7bnm_cache is not None and
                (time.monotonic() - self._wa7bnm_cache_time) < _TTL_CALENDAR):
            return self._wa7bnm_cache

        try:
            contests = await self._scrape_wa7bnm()
            self._wa7bnm_cache = contests
            self._wa7bnm_cache_time = time.monotonic()
            logger.info("Fetched %d contests from WA7BNM", len(contests))
            return contests
        except Exception as exc:
            logger.warning("WA7BNM scrape failed: %s — using hardcoded only", exc)
            return self._wa7bnm_cache or []

    async def _scrape_wa7bnm(self) -> list[ContestInfo]:
        """Scrape the WA7BNM contest calendar."""
        headers = {"User-Agent": _USER_AGENT}
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(_WA7BNM_URL, headers=headers)
            resp.raise_for_status()
            html = resp.text

        contests = []
        # Parse table rows. WA7BNM uses a simple HTML table.
        rows = re.findall(
            r'<tr[^>]*>(.*?)</tr>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 4:
                continue

            # Clean HTML tags from cell content.
            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]

            # Typical columns: Date, Time, Contest Name, Mode, ...
            if len(clean) >= 4:
                name_raw = clean[2] if len(clean) > 2 else ""
                if not name_raw or name_raw.lower() in ("contest", "name"):
                    continue

                name_slug = re.sub(r'[^A-Za-z0-9]', '-', name_raw)[:40]

                contests.append(ContestInfo(
                    name=name_slug,
                    full_name=name_raw,
                    start_utc=clean[0] + " " + (clean[1] if len(clean) > 1 else ""),
                    mode=clean[3] if len(clean) > 3 else "",
                    source="wa7bnm",
                ))

        return contests


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_service: ContestService | None = None


def get_service() -> ContestService:
    global _service
    if _service is None:
        _service = ContestService()
    return _service

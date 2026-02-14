"""Elmer — Centralised timezone configuration.

All services share ``America/Denver`` as the project-local timezone.
Internal timestamps remain UTC; this module provides helpers for
converting to local time when displaying or evaluating local-time rules
(quiet hours, cron schedules, log output).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Denver")
"""Project-wide local timezone (Mountain Time)."""

LOCAL_TZ_NAME = "America/Denver"
"""String form for libraries that accept a timezone name (e.g. APScheduler)."""


def now_local() -> datetime:
    """Return the current time in the project-local timezone (aware)."""
    return datetime.now(LOCAL_TZ)


def utc_to_local(dt: datetime) -> datetime:
    """Convert a UTC-aware datetime to the project-local timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)

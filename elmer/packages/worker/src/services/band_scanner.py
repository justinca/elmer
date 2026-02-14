"""HF band scanner — cycles through bands based on time of day and activity.

Runs in a background thread, dwelling on each band's FT8 calling frequency
for a configurable period (default 15 min).  Band order is prioritised by
propagation conditions and DX spot activity fetched from Elmer Core.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import paho.mqtt.client as mqtt

from ..config import settings
from .radio_control import RadioControl, get_radio_control

logger = logging.getLogger("elmer.band_scanner")

# ---------------------------------------------------------------------------
# Band definitions (center = FT8 calling frequency)
# ---------------------------------------------------------------------------

BAND_FREQS: dict[str, int] = {
    "10m": 28_074_000,
    "12m": 24_915_000,
    "15m": 21_074_000,
    "17m": 18_100_000,
    "20m": 14_074_000,
    "40m": 7_074_000,
    "80m": 3_573_000,
}

# Ordered high-to-low within each group.
DAYTIME_BANDS = ["10m", "12m", "15m", "17m", "20m"]
NIGHTTIME_BANDS = ["40m", "80m"]
OVERLAP_BANDS = ["20m", "40m"]

# Transition window in hours around the sunrise/sunset boundary.
_TRANSITION_HOURS = 2

# Frequency threshold for USB vs LSB.
_USB_THRESHOLD_HZ = 10_000_000

# Tolerance for manual-tune detection (Hz).
_MANUAL_TUNE_TOLERANCE = 5_000


@dataclass
class ScannerStatus:
    scanning: bool = False
    paused: bool = False
    current_band: str = ""
    current_frequency: int = 0
    band_start_time: str = ""
    dwell_seconds: int = 900
    time_remaining: int = 0
    scan_order: list[str] = field(default_factory=list)
    next_band: str = ""
    is_daytime: bool = True
    cycle_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanning": self.scanning,
            "paused": self.paused,
            "current_band": self.current_band,
            "current_frequency": self.current_frequency,
            "band_start_time": self.band_start_time,
            "dwell_seconds": self.dwell_seconds,
            "time_remaining": self.time_remaining,
            "scan_order": self.scan_order,
            "next_band": self.next_band,
            "is_daytime": self.is_daytime,
            "cycle_count": self.cycle_count,
        }


class BandScanner:
    """Background HF band scanner controlled via RadioControl."""

    def __init__(
        self,
        radio: RadioControl | None = None,
        dwell_seconds: int = 900,
        daytime_start_utc: int = 13,
        daytime_end_utc: int = 4,
    ) -> None:
        self._radio = radio or get_radio_control()
        self._dwell = dwell_seconds
        self._daytime_start = daytime_start_utc
        self._daytime_end = daytime_end_utc

        # State.
        self._scanning = False
        self._paused = False
        self._current_band = ""
        self._current_freq = 0
        self._band_start: float = 0.0
        self._scan_order: list[str] = []
        self._scan_index = 0
        self._cycle_count = 0

        # Thread management.
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, bands: list[str] | None = None) -> dict[str, Any]:
        """Begin scanning.  Optionally override band list."""
        if self._scanning:
            return {"ok": False, "error": "Scanner already running"}

        if not self._radio.connected:
            result = self._radio.connect()
            if not result.get("connected"):
                return {"ok": False, "error": "OmniRig not connected", "detail": result}

        self._scan_order = bands or self._build_scan_order()
        if not self._scan_order:
            return {"ok": False, "error": "No bands to scan"}

        self._scan_index = 0
        self._cycle_count = 0
        self._scanning = True
        self._paused = False
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._scanner_loop,
            daemon=True,
            name="band-scanner",
        )
        self._thread.start()

        logger.info("Scanner started: %s", " -> ".join(self._scan_order))
        return {
            "ok": True,
            "scan_order": self._scan_order,
            "dwell_seconds": self._dwell,
        }

    def stop(self) -> dict[str, Any]:
        """Stop scanning."""
        if not self._scanning:
            return {"ok": False, "error": "Scanner not running"}
        self._scanning = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Scanner stopped after %d cycles", self._cycle_count)
        return {"ok": True, "cycles_completed": self._cycle_count}

    def pause(self) -> dict[str, Any]:
        """Pause on current band."""
        if not self._scanning:
            return {"ok": False, "error": "Scanner not running"}
        self._paused = True
        logger.info("Scanner paused on %s", self._current_band)
        return {"ok": True, "paused_on": self._current_band}

    def resume(self) -> dict[str, Any]:
        """Resume scanning from current band."""
        if not self._scanning:
            return {"ok": False, "error": "Scanner not running"}
        self._paused = False
        # Reset dwell timer so we start fresh on current band.
        self._band_start = time.time()
        logger.info("Scanner resumed on %s", self._current_band)
        return {"ok": True, "resumed_on": self._current_band}

    def next_band(self) -> dict[str, Any]:
        """Skip to the next band immediately."""
        if not self._scanning:
            return {"ok": False, "error": "Scanner not running"}
        self._band_start = 0  # Force immediate advance.
        self._paused = False
        return {"ok": True}

    def set_dwell_time(self, seconds: int) -> dict[str, Any]:
        """Change dwell time."""
        if seconds < 10:
            return {"ok": False, "error": "Minimum dwell is 10 seconds"}
        self._dwell = seconds
        logger.info("Dwell time set to %ds", seconds)
        return {"ok": True, "dwell_seconds": seconds}

    def get_status(self) -> ScannerStatus:
        """Build current status snapshot."""
        now = time.time()
        elapsed = now - self._band_start if self._band_start else 0
        remaining = max(0, self._dwell - int(elapsed)) if self._scanning else 0

        next_idx = (self._scan_index + 1) % len(self._scan_order) if self._scan_order else 0
        next_b = self._scan_order[next_idx] if self._scan_order else ""

        return ScannerStatus(
            scanning=self._scanning,
            paused=self._paused,
            current_band=self._current_band,
            current_frequency=self._current_freq,
            band_start_time=datetime.fromtimestamp(self._band_start, tz=timezone.utc).isoformat() if self._band_start else "",
            dwell_seconds=self._dwell,
            time_remaining=remaining,
            scan_order=list(self._scan_order),
            next_band=next_b,
            is_daytime=self._is_daytime(),
            cycle_count=self._cycle_count,
        )

    # ------------------------------------------------------------------
    # Time-of-day helpers
    # ------------------------------------------------------------------

    def _is_daytime(self) -> bool:
        """Determine if it's daytime based on UTC hour boundaries.

        Daytime window wraps around midnight UTC when start > end.
        e.g. start=13 end=4 means 13:00-03:59 UTC is daytime.
        """
        hour = datetime.now(timezone.utc).hour
        if self._daytime_start <= self._daytime_end:
            return self._daytime_start <= hour < self._daytime_end
        else:
            return hour >= self._daytime_start or hour < self._daytime_end

    def _is_transition(self) -> bool:
        """Check if we're within the transition window around sunrise/sunset."""
        hour = datetime.now(timezone.utc).hour
        # Transition around daytime start (sunrise).
        for boundary in (self._daytime_start, self._daytime_end):
            for offset in range(-_TRANSITION_HOURS, _TRANSITION_HOURS + 1):
                if hour == (boundary + offset) % 24:
                    return True
        return False

    # ------------------------------------------------------------------
    # Band ordering / prioritisation
    # ------------------------------------------------------------------

    def _build_scan_order(self) -> list[str]:
        """Build prioritised band list based on time-of-day and conditions."""
        # Base list for time of day.
        if self._is_daytime():
            base = list(DAYTIME_BANDS)
        else:
            base = list(NIGHTTIME_BANDS)

        # Add overlap bands during transitions.
        if self._is_transition():
            for b in OVERLAP_BANDS:
                if b not in base:
                    base.append(b)
            # Re-sort high-to-low by frequency.
            base.sort(key=lambda b: BAND_FREQS.get(b, 0), reverse=True)

        # Try to prioritise by propagation + spot activity.
        try:
            base = self._prioritise_bands(base)
        except Exception:
            logger.debug("Band prioritisation failed, using base order", exc_info=True)

        return base

    def _prioritise_bands(self, bands: list[str]) -> list[str]:
        """Re-order bands by propagation conditions and DX spot counts."""
        prop = self._fetch_propagation()
        spots = self._fetch_spot_summary()

        if not prop and not spots:
            return bands

        # Assign a score: higher = scan first.
        # Condition score: good=3, fair=2, poor=1, unknown=0
        cond_score = {"good": 3, "fair": 2, "poor": 1}
        # Within each priority group, keep high-to-low freq order.

        scored: list[tuple[str, int]] = []
        for i, band in enumerate(bands):
            score = 0

            # Propagation condition.
            if prop:
                band_data = prop.get(band, {})
                day_cond = band_data.get("day", "").lower()
                night_cond = band_data.get("night", "").lower()
                relevant = day_cond if self._is_daytime() else night_cond
                score += cond_score.get(relevant, 0) * 100

            # DX spot activity.
            if spots:
                spot_count = spots.get(band, 0)
                score += min(spot_count, 50)  # Cap at 50 to not overwhelm condition.

            # Tiebreaker: preserve original (high-to-low) order.
            score -= i

            scored.append((band, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [b for b, _ in scored]

    def _fetch_propagation(self) -> dict[str, Any] | None:
        """Fetch band conditions from Elmer Core."""
        try:
            url = f"{settings.core_base_url}/propagation/bands"
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                return data.get("bands", data) if isinstance(data, dict) else None
        except Exception:
            logger.debug("Failed to fetch propagation data", exc_info=True)
            return None

    def _fetch_spot_summary(self) -> dict[str, int] | None:
        """Fetch DX spot counts per band from Elmer Core."""
        try:
            url = f"{settings.core_base_url}/dx/spots/summary"
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
                # Expect {"bands": {"20m": 42, ...}} or flat dict.
                if isinstance(data, dict):
                    return data.get("bands", data)
                return None
        except Exception:
            logger.debug("Failed to fetch spot summary", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Scanner loop (runs in background thread)
    # ------------------------------------------------------------------

    def _scanner_loop(self) -> None:
        """Main scanning loop — runs until stop_event is set."""
        # Tune to first band.
        self._tune_to_band(self._scan_order[self._scan_index])
        self._band_start = time.time()

        while not self._stop_event.is_set():
            # Check for manual frequency change (someone touched the dial).
            if not self._paused:
                actual_freq = self._radio.get_frequency()
                if actual_freq is not None and self._current_freq > 0:
                    if abs(actual_freq - self._current_freq) > _MANUAL_TUNE_TOLERANCE:
                        logger.info(
                            "Manual frequency change detected: %d -> %d",
                            self._current_freq, actual_freq,
                        )
                        self._paused = True
                        self._publish_mqtt("elmer/radio/scanner-paused", {
                            "reason": "manual_tune",
                            "detected_frequency": actual_freq,
                            "expected_frequency": self._current_freq,
                        })

            # Advance band if dwell time exceeded and not paused.
            if not self._paused:
                elapsed = time.time() - self._band_start
                if elapsed >= self._dwell:
                    self._advance_band()

            # Sleep in small increments for responsive shutdown.
            self._stop_event.wait(timeout=1.0)

        logger.info("Scanner loop exited")

    def _advance_band(self) -> None:
        """Move to the next band in scan_order."""
        self._scan_index += 1

        # End of cycle — rebuild order (re-check propagation / time-of-day).
        if self._scan_index >= len(self._scan_order):
            self._scan_index = 0
            self._cycle_count += 1
            new_order = self._build_scan_order()
            if new_order:
                self._scan_order = new_order
                logger.info(
                    "Cycle %d complete, rebuilt order: %s",
                    self._cycle_count, " -> ".join(self._scan_order),
                )

        self._tune_to_band(self._scan_order[self._scan_index])
        self._band_start = time.time()

    def _tune_to_band(self, band: str) -> None:
        """Set radio to band center frequency and appropriate mode."""
        freq = BAND_FREQS.get(band)
        if freq is None:
            logger.warning("Unknown band: %s", band)
            return

        # Set mode: USB above 10 MHz, LSB below.
        mode = "USB" if freq >= _USB_THRESHOLD_HZ else "LSB"

        result = self._radio.set_frequency(freq)
        if not result.get("ok"):
            logger.error("Failed to tune to %s (%d Hz): %s", band, freq, result)
            return

        self._radio.set_mode(mode)

        self._current_band = band
        self._current_freq = freq

        logger.info("Tuned to %s: %d Hz %s", band, freq, mode)

        self._publish_mqtt("elmer/radio/band-change", {
            "band": band,
            "frequency_hz": freq,
            "mode": mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ------------------------------------------------------------------
    # MQTT publishing (fire-and-forget in background)
    # ------------------------------------------------------------------

    def _publish_mqtt(self, topic: str, payload: dict) -> None:
        """Publish a message via a short-lived MQTT connection."""
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            if settings.MQTT_USER:
                client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD or None)
            client.connect(settings.MQTT_HOST, settings.MQTT_PORT)
            client.publish(topic, json.dumps(payload, default=str))
            client.disconnect()
        except Exception:
            logger.debug("MQTT publish to %s failed", topic, exc_info=True)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: BandScanner | None = None


def get_band_scanner() -> BandScanner:
    """Return the shared BandScanner instance."""
    global _instance
    if _instance is None:
        _instance = BandScanner(
            dwell_seconds=settings.SCANNER_DWELL_SECONDS,
            daytime_start_utc=settings.SCANNER_DAYTIME_START_UTC,
            daytime_end_utc=settings.SCANNER_DAYTIME_END_UTC,
        )
    return _instance

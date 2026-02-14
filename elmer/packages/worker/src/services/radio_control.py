"""OmniRig radio control service for SDR Console.

Wraps the omnipyrig library to control SDR Console via OmniRig's COM
interface on Windows.  OmniRig must be running before this service is used.

Note: omnipyrig uses Windows COM automation (win32com) so this module
only works on Windows — which is fine since the Worker runs on Windows.
"""

import logging
from typing import Any

logger = logging.getLogger("elmer.radio_control")

# Mode mappings: our label -> omnipyrig constant name
_MODE_MAP = {
    "USB": "MODE_SSB_U",
    "LSB": "MODE_SSB_L",
    "CW": "MODE_CW_U",
    "CW-R": "MODE_CW_L",
    "AM": "MODE_AM",
    "FM": "MODE_FM",
}

# Reverse map built lazily after omnipyrig is imported.
_REVERSE_MODE_MAP: dict[int, str] | None = None


class RadioControl:
    """Interface to OmniRig for controlling SDR Console."""

    def __init__(self, rig_number: int = 1) -> None:
        self._rig_number = rig_number
        self._omni: Any = None
        self._connected = False
        self._rig_type: str = "unknown"

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> dict[str, Any]:
        """Initialize OmniRig connection and verify it responds.

        Returns a status dict with rig info or error details.
        """
        try:
            import omnipyrig

            self._omni = omnipyrig.OmniRigWrapper()
            self._omni.setActiveRig(self._rig_number)

            rig_type = self._omni.getParam("RigType")
            self._rig_type = str(rig_type) if rig_type else "unknown"
            self._connected = True

            logger.info(
                "OmniRig connected: rig %d, type=%s",
                self._rig_number,
                self._rig_type,
            )
            return {
                "connected": True,
                "rig_number": self._rig_number,
                "rig_type": self._rig_type,
            }

        except Exception as exc:
            self._connected = False
            logger.error("OmniRig connection failed: %s", exc)
            return {
                "connected": False,
                "rig_number": self._rig_number,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    def set_frequency(self, freq_hz: int) -> dict[str, Any]:
        """Set VFO-A frequency in Hz."""
        if not self._connected or self._omni is None:
            return {"ok": False, "error": "OmniRig not connected"}
        try:
            self._omni.setFrequency("A", freq_hz)
            logger.info("Frequency set to %d Hz", freq_hz)
            return {"ok": True, "frequency_hz": freq_hz}
        except Exception as exc:
            logger.error("Failed to set frequency: %s", exc)
            return {"ok": False, "error": str(exc)}

    def get_frequency(self) -> int | None:
        """Read current VFO-A frequency in Hz."""
        if not self._connected or self._omni is None:
            return None
        try:
            freq = self._omni.getParam("FreqA")
            if freq is None:
                freq = self._omni.getParam("Freq")
            return int(freq) if freq else None
        except Exception as exc:
            logger.error("Failed to read frequency: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> dict[str, Any]:
        """Set operating mode (USB, LSB, CW, AM, FM)."""
        if not self._connected or self._omni is None:
            return {"ok": False, "error": "OmniRig not connected"}

        mode_upper = mode.upper()
        attr_name = _MODE_MAP.get(mode_upper)
        if attr_name is None:
            return {"ok": False, "error": f"Unknown mode: {mode}"}

        try:
            import omnipyrig

            mode_value = getattr(omnipyrig, attr_name, None)
            if mode_value is None:
                mode_value = getattr(self._omni, attr_name, None)
            if mode_value is None:
                return {"ok": False, "error": f"Mode constant {attr_name} not found in omnipyrig"}

            self._omni.setMode(mode_value)
            logger.info("Mode set to %s", mode_upper)
            return {"ok": True, "mode": mode_upper}
        except Exception as exc:
            logger.error("Failed to set mode: %s", exc)
            return {"ok": False, "error": str(exc)}

    def get_mode(self) -> str | None:
        """Read current operating mode as a string."""
        if not self._connected or self._omni is None:
            return None
        try:
            import omnipyrig

            global _REVERSE_MODE_MAP
            if _REVERSE_MODE_MAP is None:
                _REVERSE_MODE_MAP = {}
                for label, attr in _MODE_MAP.items():
                    val = getattr(omnipyrig, attr, None)
                    if val is None:
                        val = getattr(self._omni, attr, None)
                    if val is not None:
                        _REVERSE_MODE_MAP[int(val)] = label

            raw = self._omni.getParam("Mode")
            if raw is None:
                return None
            return _REVERSE_MODE_MAP.get(int(raw), f"UNKNOWN({raw})")
        except Exception as exc:
            logger.error("Failed to read mode: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return current radio status dict."""
        freq = self.get_frequency()
        mode = self.get_mode()
        return {
            "connected": self._connected,
            "rig_number": self._rig_number,
            "rig_type": self._rig_type,
            "frequency_hz": freq,
            "mode": mode,
        }

    @property
    def connected(self) -> bool:
        return self._connected


# ---------------------------------------------------------------------------
# Module-level singleton (lazy-init, like other worker services)
# ---------------------------------------------------------------------------

_instance: RadioControl | None = None


def get_radio_control(rig_number: int = 1) -> RadioControl:
    """Return the shared RadioControl instance."""
    global _instance
    if _instance is None:
        _instance = RadioControl(rig_number)
    return _instance

"""Kenwood TS-2000 CAT control for SDR Console.

Sends CAT commands over TCP to SDR Console, which emulates a Kenwood
TS-2000.  No COM/OmniRig dependency — just a plain TCP socket.

TS-2000 CAT command reference (subset used here):
  FA00014074000;   Set VFO-A frequency (11-digit Hz)
  FA;              Read VFO-A frequency -> FA00014074000;
  MD2;             Set mode (1=LSB 2=USB 3=CW 4=FM 5=AM 7=CW-R)
  MD;              Read mode -> MD2;
  ID;              Read rig ID -> ID019; (TS-2000)
"""

import logging
import socket
import threading
from typing import Any

logger = logging.getLogger("elmer.radio_control")

# TS-2000 mode numbers.
_MODE_TO_CAT: dict[str, str] = {
    "LSB": "1",
    "USB": "2",
    "CW": "3",
    "FM": "4",
    "AM": "5",
    "CW-R": "7",
}

_CAT_TO_MODE: dict[str, str] = {v: k for k, v in _MODE_TO_CAT.items()}

# Socket timeout for CAT commands.
_SOCK_TIMEOUT = 3.0


class RadioControl:
    """CAT control interface to SDR Console (TS-2000 emulation) over TCP."""

    def __init__(self, host: str = "localhost", port: int = 7356) -> None:
        self._host = host
        self._port = port
        self._connected = False
        self._rig_id: str = ""
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Low-level CAT I/O
    # ------------------------------------------------------------------

    def _send_cmd(self, cmd: str) -> str:
        """Send a CAT command and return the response.

        Opens a fresh TCP connection for each command to avoid stale
        socket issues with SDR Console's CAT server.
        """
        with self._lock:
            try:
                with socket.create_connection(
                    (self._host, self._port), timeout=_SOCK_TIMEOUT
                ) as sock:
                    sock.sendall(cmd.encode("ascii"))

                    # Read until we get a semicolon terminator.
                    buf = b""
                    while b";" not in buf:
                        chunk = sock.recv(256)
                        if not chunk:
                            break
                        buf += chunk

                    resp = buf.decode("ascii").strip()
                    logger.debug("CAT %s -> %s", cmd.rstrip(";"), resp)
                    return resp

            except (OSError, socket.timeout) as exc:
                logger.error("CAT command '%s' failed: %s", cmd.rstrip(";"), exc)
                self._connected = False
                raise

    def _send_cmd_no_reply(self, cmd: str) -> None:
        """Send a CAT set-command that has no response."""
        with self._lock:
            try:
                with socket.create_connection(
                    (self._host, self._port), timeout=_SOCK_TIMEOUT
                ) as sock:
                    sock.sendall(cmd.encode("ascii"))
            except (OSError, socket.timeout) as exc:
                logger.error("CAT command '%s' failed: %s", cmd.rstrip(";"), exc)
                self._connected = False
                raise

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> dict[str, Any]:
        """Verify the CAT connection by reading the rig ID."""
        try:
            resp = self._send_cmd("ID;")
            # TS-2000 returns "ID019;"
            self._rig_id = resp.replace(";", "")
            self._connected = True
            logger.info("CAT connected to %s:%d (ID=%s)", self._host, self._port, self._rig_id)
            return {
                "connected": True,
                "host": self._host,
                "port": self._port,
                "rig_id": self._rig_id,
            }
        except Exception as exc:
            self._connected = False
            logger.error("CAT connection failed to %s:%d: %s", self._host, self._port, exc)
            return {
                "connected": False,
                "host": self._host,
                "port": self._port,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    def set_frequency(self, freq_hz: int) -> dict[str, Any]:
        """Set VFO-A frequency in Hz."""
        try:
            cmd = f"FA{freq_hz:011d};"
            self._send_cmd_no_reply(cmd)
            logger.info("Frequency set to %d Hz", freq_hz)
            return {"ok": True, "frequency_hz": freq_hz}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_frequency(self) -> int | None:
        """Read current VFO-A frequency in Hz."""
        try:
            resp = self._send_cmd("FA;")
            # Response: "FA00014074000;"
            digits = resp.replace("FA", "").replace(";", "")
            return int(digits) if digits.isdigit() else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> dict[str, Any]:
        """Set operating mode (USB, LSB, CW, AM, FM, CW-R)."""
        mode_upper = mode.upper()
        cat_num = _MODE_TO_CAT.get(mode_upper)
        if cat_num is None:
            return {"ok": False, "error": f"Unknown mode: {mode}"}
        try:
            self._send_cmd_no_reply(f"MD{cat_num};")
            logger.info("Mode set to %s", mode_upper)
            return {"ok": True, "mode": mode_upper}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_mode(self) -> str | None:
        """Read current operating mode as a string."""
        try:
            resp = self._send_cmd("MD;")
            # Response: "MD2;"
            num = resp.replace("MD", "").replace(";", "").strip()
            return _CAT_TO_MODE.get(num, f"UNKNOWN({num})")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return current radio status dict."""
        if not self._connected:
            return {
                "connected": False,
                "host": self._host,
                "port": self._port,
                "rig_id": self._rig_id,
                "frequency_hz": None,
                "mode": None,
            }
        freq = self.get_frequency()
        mode = self.get_mode()
        return {
            "connected": self._connected,
            "host": self._host,
            "port": self._port,
            "rig_id": self._rig_id,
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


def get_radio_control(host: str = "localhost", port: int = 7356) -> RadioControl:
    """Return the shared RadioControl instance."""
    global _instance
    if _instance is None:
        _instance = RadioControl(host, port)
    return _instance

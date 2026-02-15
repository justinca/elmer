"""Kenwood TS-2000 CAT control for SDR Console via virtual serial port.

Sends CAT commands over a virtual COM port (com0com) to SDR Console,
which emulates a Kenwood TS-2000.

Setup:
  1. Create a com0com port pair (e.g. COM10 <-> COM11)
  2. Configure SDR Console CAT to use COM10, 57600 baud, 8N1, Kenwood TS-2000
  3. Set CAT_COM_PORT=COM11 in Worker .env (the other end of the pair)

TS-2000 CAT command reference (subset used here):
  FA00014074000;   Set VFO-A frequency (11-digit Hz)
  FA;              Read VFO-A frequency -> FA00014074000;
  MD2;             Set mode (1=LSB 2=USB 3=CW 4=FM 5=AM 7=CW-R)
  MD;              Read mode -> MD2;
  ID;              Read rig ID -> ID019; (TS-2000)
"""

import logging
import threading
from typing import Any

import serial

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

# Serial read timeout (seconds).
_SERIAL_TIMEOUT = 3.0


class RadioControl:
    """CAT control interface to SDR Console (TS-2000 emulation) over serial."""

    def __init__(self, port: str = "COM11", baud: int = 57600) -> None:
        self._port = port
        self._baud = baud
        self._connected = False
        self._rig_id: str = ""
        self._lock = threading.Lock()
        self._ser: serial.Serial | None = None

    # ------------------------------------------------------------------
    # Low-level CAT I/O
    # ------------------------------------------------------------------

    def _open(self) -> serial.Serial:
        """Return the open serial connection, creating it if needed."""
        if self._ser is not None and self._ser.is_open:
            return self._ser
        self._ser = serial.Serial(
            port=self._port,
            baudrate=self._baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=_SERIAL_TIMEOUT,
        )
        logger.info("Serial port %s opened at %d baud", self._port, self._baud)
        return self._ser

    def _close(self) -> None:
        """Close the serial connection."""
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def _send_cmd(self, cmd: str) -> str:
        """Send a CAT command and return the response (up to semicolon)."""
        with self._lock:
            try:
                ser = self._open()
                ser.write(cmd.encode("ascii"))

                # Read until we get a semicolon terminator.
                buf = b""
                while b";" not in buf:
                    chunk = ser.read(1)
                    if not chunk:
                        break  # timeout
                    buf += chunk

                resp = buf.decode("ascii").strip()
                logger.debug("CAT %s -> %s", cmd.rstrip(";"), resp)
                return resp

            except (OSError, serial.SerialException) as exc:
                logger.error("CAT command '%s' failed: %s", cmd.rstrip(";"), exc)
                self._connected = False
                self._close()
                raise

    def _send_cmd_no_reply(self, cmd: str) -> None:
        """Send a CAT set-command that has no response."""
        with self._lock:
            try:
                ser = self._open()
                ser.write(cmd.encode("ascii"))
            except (OSError, serial.SerialException) as exc:
                logger.error("CAT command '%s' failed: %s", cmd.rstrip(";"), exc)
                self._connected = False
                self._close()
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
            logger.info("CAT connected on %s (ID=%s)", self._port, self._rig_id)
            return {
                "connected": True,
                "port": self._port,
                "baud": self._baud,
                "rig_id": self._rig_id,
            }
        except Exception as exc:
            self._connected = False
            logger.error("CAT connection failed on %s: %s", self._port, exc)
            return {
                "connected": False,
                "port": self._port,
                "baud": self._baud,
                "error": str(exc),
            }

    def disconnect(self) -> None:
        """Close the serial port."""
        self._close()
        self._connected = False

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
                "port": self._port,
                "baud": self._baud,
                "rig_id": self._rig_id,
                "frequency_hz": None,
                "mode": None,
            }
        freq = self.get_frequency()
        mode = self.get_mode()
        return {
            "connected": self._connected,
            "port": self._port,
            "baud": self._baud,
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


def get_radio_control(port: str = "COM11", baud: int = 57600) -> RadioControl:
    """Return the shared RadioControl instance."""
    global _instance
    if _instance is None:
        _instance = RadioControl(port, baud)
    return _instance

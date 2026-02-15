"""Radio control and band scanner endpoints.

Exposes CAT radio control and the HF band scanner via REST.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.radio_control import get_radio_control
from ..services.band_scanner import get_band_scanner

logger = logging.getLogger("elmer.worker.radio")

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class FrequencyRequest(BaseModel):
    frequency_hz: int


class ModeRequest(BaseModel):
    mode: str


class ScannerStartRequest(BaseModel):
    dwell_seconds: int | None = None
    bands: list[str] | None = None


class DwellRequest(BaseModel):
    seconds: int


# ---------------------------------------------------------------------------
# Radio control endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def radio_status():
    """CAT connection status, current frequency and mode."""
    rc = get_radio_control()
    return rc.get_status()


@router.post("/connect")
async def radio_connect():
    """Attempt to (re)connect the CAT serial port."""
    rc = get_radio_control()
    result = rc.connect()
    if not result.get("connected"):
        raise HTTPException(status_code=503, detail=result.get("error", "Connection failed"))
    return result


@router.post("/frequency")
async def set_frequency(req: FrequencyRequest):
    """Set VFO-A frequency."""
    rc = get_radio_control()
    if not rc.connected:
        raise HTTPException(status_code=503, detail="CAT not connected")
    result = rc.set_frequency(req.frequency_hz)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed"))
    return result


@router.post("/mode")
async def set_mode(req: ModeRequest):
    """Set operating mode (USB, LSB, CW, AM, FM)."""
    rc = get_radio_control()
    if not rc.connected:
        raise HTTPException(status_code=503, detail="CAT not connected")
    result = rc.set_mode(req.mode)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result


# ---------------------------------------------------------------------------
# Scanner endpoints
# ---------------------------------------------------------------------------

@router.get("/scanner/status")
async def scanner_status():
    """Band scanner state — scanning, band, time remaining, order."""
    scanner = get_band_scanner()
    return scanner.get_status().to_dict()


@router.post("/scanner/start")
async def scanner_start(req: ScannerStartRequest | None = None):
    """Start the band scanner."""
    scanner = get_band_scanner()
    if req and req.dwell_seconds:
        scanner.set_dwell_time(req.dwell_seconds)
    bands = req.bands if req else None
    result = scanner.start(bands=bands)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result


@router.post("/scanner/stop")
async def scanner_stop():
    """Stop the band scanner."""
    scanner = get_band_scanner()
    result = scanner.stop()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result


@router.post("/scanner/pause")
async def scanner_pause():
    """Pause on current band."""
    scanner = get_band_scanner()
    result = scanner.pause()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result


@router.post("/scanner/resume")
async def scanner_resume():
    """Resume scanning."""
    scanner = get_band_scanner()
    result = scanner.resume()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result


@router.post("/scanner/next")
async def scanner_next():
    """Skip to the next band immediately."""
    scanner = get_band_scanner()
    result = scanner.next_band()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result


@router.post("/scanner/dwell")
async def scanner_dwell(req: DwellRequest):
    """Change dwell time (seconds)."""
    scanner = get_band_scanner()
    result = scanner.set_dwell_time(req.seconds)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed"))
    return result

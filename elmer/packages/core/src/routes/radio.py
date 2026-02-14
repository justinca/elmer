"""Radio control proxy — forwards requests to the Worker's /radio/ endpoints.

The Worker controls SDR Console via OmniRig on the Windows machine.
Core acts as a gateway so dashboard, Telegram, and agents can reach it.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..config import settings

router = APIRouter(prefix="/radio", tags=["radio"])
logger = logging.getLogger("elmer.radio")

_WORKER_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Proxy helpers
# ---------------------------------------------------------------------------

async def _proxy_get(path: str, timeout: float = _WORKER_TIMEOUT) -> Any:
    """Proxy a GET request to the Worker's /radio/ endpoints."""
    url = f"{settings.worker_base_url}/radio{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Worker unreachable at {settings.worker_base_url} — is it running?",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Worker request timed out")


async def _proxy_post(path: str, body: dict | None = None, timeout: float = _WORKER_TIMEOUT) -> Any:
    """Proxy a POST request to the Worker's /radio/ endpoints."""
    url = f"{settings.worker_base_url}/radio{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Worker unreachable at {settings.worker_base_url} — is it running?",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Worker request timed out")


# ---------------------------------------------------------------------------
# Radio control
# ---------------------------------------------------------------------------

@router.get("/status")
async def radio_status():
    """OmniRig status — frequency, mode, connection."""
    return await _proxy_get("/status")


@router.post("/frequency")
async def set_frequency(request: Request):
    """Set VFO-A frequency.  Body: {"frequency_hz": 14074000}"""
    body = await request.json()
    return await _proxy_post("/frequency", body)


@router.post("/mode")
async def set_mode(request: Request):
    """Set operating mode.  Body: {"mode": "USB"}"""
    body = await request.json()
    return await _proxy_post("/mode", body)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

@router.get("/scanner/status")
async def scanner_status():
    """Band scanner state — scanning, band, time remaining, order."""
    return await _proxy_get("/scanner/status")


@router.post("/scanner/start")
async def scanner_start(request: Request):
    """Start the band scanner.  Optional body: {"dwell_seconds": 900, "bands": ["20m"]}"""
    try:
        body = await request.json()
    except Exception:
        body = None
    return await _proxy_post("/scanner/start", body)


@router.post("/scanner/stop")
async def scanner_stop():
    """Stop the band scanner."""
    return await _proxy_post("/scanner/stop")


@router.post("/scanner/pause")
async def scanner_pause():
    """Pause on current band."""
    return await _proxy_post("/scanner/pause")


@router.post("/scanner/resume")
async def scanner_resume():
    """Resume scanning."""
    return await _proxy_post("/scanner/resume")


@router.post("/scanner/next")
async def scanner_next():
    """Skip to next band immediately."""
    return await _proxy_post("/scanner/next")


@router.post("/scanner/dwell")
async def scanner_dwell(request: Request):
    """Change dwell time.  Body: {"seconds": 900}"""
    body = await request.json()
    return await _proxy_post("/scanner/dwell", body)

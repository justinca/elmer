"""Log endpoints — Log4OM proxy, LLM analysis, knowledge sync, needs cross-reference.

Proxies read-only QSO data from the Worker's /log4om/ endpoints and adds
core-only features: knowledge base sync, LLM-based analysis, and DXCC
needs list cross-referencing.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..config import settings

router = APIRouter(prefix="/log", tags=["log"])
logger = logging.getLogger("elmer.log")

_WORKER_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Worker proxy helper
# ---------------------------------------------------------------------------

async def _proxy_worker(
    path: str,
    params: dict[str, Any] | None = None,
    timeout: float = _WORKER_TIMEOUT,
) -> Any:
    """Proxy a GET request to the worker's /log4om/ endpoints."""
    url = f"{settings.worker_base_url}/log4om{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
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
        raise HTTPException(
            status_code=504,
            detail="Worker request timed out",
        )


# ---------------------------------------------------------------------------
# Proxy endpoints (Worker pass-through)
# ---------------------------------------------------------------------------

@router.get("/status")
async def log_status():
    """Log4OM database status (proxied from worker)."""
    return await _proxy_worker("/status")


@router.get("/qsos")
async def get_qsos(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    call: str | None = Query(default=None),
    band: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    country: str | None = Query(default=None),
    since: str | None = Query(default=None, description="YYYY-MM-DD"),
    until: str | None = Query(default=None, description="YYYY-MM-DD"),
):
    """Fetch QSOs with filters (proxied from worker)."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if call:
        params["call"] = call
    if band:
        params["band"] = band
    if mode:
        params["mode"] = mode
    if country:
        params["country"] = country
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    return await _proxy_worker("/qsos", params=params)


@router.get("/qsos/count")
async def get_qso_count(
    call: str | None = Query(default=None),
    band: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    country: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
):
    """QSO count with optional filters (proxied from worker)."""
    params: dict[str, Any] = {}
    if call:
        params["call"] = call
    if band:
        params["band"] = band
    if mode:
        params["mode"] = mode
    if country:
        params["country"] = country
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    return await _proxy_worker("/qsos/count", params=params)


@router.get("/stats")
async def get_stats():
    """Aggregate log statistics (proxied from worker)."""
    return await _proxy_worker("/stats")


@router.get("/dxcc")
async def get_dxcc():
    """DXCC entity summary (proxied from worker)."""
    return await _proxy_worker("/dxcc")


@router.get("/search")
async def search_qsos(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Full-text search across QSO fields (proxied from worker)."""
    return await _proxy_worker("/search", params={"q": q, "limit": limit})


@router.get("/contests")
async def get_contests():
    """Contest participation summary (proxied from worker)."""
    return await _proxy_worker("/contests")


@router.get("/recent")
async def get_recent(limit: int = Query(default=20, ge=1, le=100)):
    """Most recent QSOs (proxied from worker)."""
    return await _proxy_worker("/recent", params={"limit": limit})


# ---------------------------------------------------------------------------
# Core-only endpoints
# ---------------------------------------------------------------------------

@router.post("/sync")
async def sync_log_to_knowledge():
    """Sync recent QSO daily summaries into the knowledge base for RAG."""
    from ..services.log_analyzer import sync_log_summaries

    try:
        return await sync_log_summaries()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Worker unreachable — cannot fetch log data for sync",
        )
    except Exception as exc:
        logger.exception("Log sync failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze")
async def analyze_log(
    days: int = Query(default=30, ge=1, le=365),
    focus: str | None = Query(default=None, description="Analysis focus area"),
):
    """LLM-based analysis of recent log activity."""
    from ..services.log_analyzer import analyze_log_activity

    try:
        return await analyze_log_activity(days=days, focus=focus)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Worker unreachable — cannot fetch log data for analysis",
        )
    except Exception as exc:
        logger.exception("Log analysis failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/needs-check")
async def check_needs_against_log():
    """Cross-reference DXCC needs list against worked entities in the log."""
    from ..services.log_analyzer import cross_reference_needs

    try:
        return await cross_reference_needs()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Worker unreachable — cannot fetch DXCC data",
        )
    except Exception as exc:
        logger.exception("Needs check failed")
        raise HTTPException(status_code=500, detail=str(exc))

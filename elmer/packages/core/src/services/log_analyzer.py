"""Log analyzer — LLM analysis, knowledge-base sync, and needs cross-reference.

Fetches QSO data from the worker's /log4om/ endpoints and provides:
  - LLM-based analysis of recent log activity
  - Daily summary sync into the knowledge base for RAG
  - Cross-reference of DXCC needs list against worked entities
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import settings
from ..services import db

logger = logging.getLogger("elmer.log_analyzer")

_WORKER_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
_LLM_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0)


# ---------------------------------------------------------------------------
# Worker fetch helpers
# ---------------------------------------------------------------------------

async def _fetch_worker(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET a worker /log4om/ endpoint."""
    url = f"{settings.worker_base_url}/log4om{path}"
    async with httpx.AsyncClient(timeout=_WORKER_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _llm_chat(prompt: str, system: str | None = None) -> str:
    """Send a prompt to the LLM via the worker's /llm/chat endpoint."""
    url = f"{settings.worker_base_url}/llm/chat"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": "llama3.1:8b",
        "messages": messages,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", data.get("response", ""))


# ---------------------------------------------------------------------------
# Embedding helpers (reuse pattern from knowledge.py)
# ---------------------------------------------------------------------------

async def _get_embedding(text: str) -> list[float]:
    """Generate embedding via worker, fallback to direct Ollama."""
    worker_url = f"{settings.worker_base_url}/llm/embed"
    ollama_url = f"{settings.ollama_base_url}/api/embed"
    payload = {"model": "nomic-embed-text", "input": text}

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)) as client:
        try:
            resp = await client.post(worker_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker embed failed (%s), falling back to Ollama", exc)

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)) as client:
        resp = await client.post(ollama_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise RuntimeError("No embeddings returned")
        return embeddings[0]


def _chunk_text(text: str, chunk_size: int = 500) -> list[dict[str, Any]]:
    """Split text into chunks by paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [{"text": text, "index": 0}]

    chunks: list[dict[str, Any]] = []
    current = ""
    idx = 0

    for para in paragraphs:
        if current and len(current) + len(para) + 2 > chunk_size:
            chunks.append({"text": current.strip(), "index": idx})
            idx += 1
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip():
        chunks.append({"text": current.strip(), "index": idx})

    return chunks


# ---------------------------------------------------------------------------
# analyze_log_activity
# ---------------------------------------------------------------------------

async def analyze_log_activity(
    days: int = 30,
    focus: str | None = None,
) -> dict[str, Any]:
    """LLM-based analysis of recent log activity."""
    since = (date.today() - timedelta(days=days)).isoformat()

    # Fetch stats and recent QSOs from worker.
    stats = await _fetch_worker("/stats")
    qsos = await _fetch_worker("/qsos", params={
        "since": since, "limit": 200,
    })
    dxcc = await _fetch_worker("/dxcc")

    # Build compact QSO summary for the prompt.
    qso_list = qsos if isinstance(qsos, list) else qsos.get("qsos", [])
    qso_lines = []
    for q in qso_list[:100]:
        line = f"- {q.get('qso_date', '?')} {q.get('call', '?')} {q.get('band', '')} {q.get('mode', '')} {q.get('country', '')}"
        qso_lines.append(line)

    dxcc_list = dxcc if isinstance(dxcc, list) else dxcc.get("entities", [])
    entity_count = len(dxcc_list)

    prompt = f"""Analyze the following amateur radio (ham radio) log data for callsign W0ABE.

## Statistics
{json.dumps(stats, indent=2, default=str)}

## DXCC Summary
Total unique DXCC entities worked: {entity_count}

## Recent QSOs (last {days} days, up to 100 shown)
{chr(10).join(qso_lines) if qso_lines else "No QSOs in this period."}

## Analysis Request
Provide a concise analysis covering:
1. Activity level and trends
2. Band and mode preferences
3. Notable DX worked
4. Suggestions for improvement or new targets
"""
    if focus:
        prompt += f"\nFocus especially on: {focus}\n"

    system_msg = (
        "You are Elmer, an expert ham radio assistant for W0ABE. "
        "Analyze the operator's log data and provide actionable insights. "
        "Be concise and specific. Use ham radio terminology appropriately."
    )

    analysis = await _llm_chat(prompt, system=system_msg)

    return {
        "analysis": analysis,
        "days_analyzed": days,
        "qso_count": len(qso_list),
        "stats_summary": {
            "total_qsos": stats.get("total_qsos", 0),
            "unique_countries": stats.get("unique_countries", 0),
            "unique_calls": stats.get("unique_calls", 0),
            "dxcc_entities": entity_count,
        },
    }


# ---------------------------------------------------------------------------
# sync_log_summaries
# ---------------------------------------------------------------------------

async def sync_log_summaries() -> dict[str, Any]:
    """Sync daily QSO summaries into the knowledge base for RAG."""
    # Find last sync date.
    last_row = await db.fetch_one(
        """SELECT MAX(source_path) AS last_path
           FROM elmer.documents
           WHERE source = 'log4om-daily'"""
    )

    if last_row and last_row["last_path"]:
        # Parse date from source_path like "log-2024-01-15#chunk-0"
        try:
            date_str = last_row["last_path"].split("#")[0].replace("log-", "")
            last_date = date.fromisoformat(date_str)
        except (ValueError, IndexError):
            last_date = date.today() - timedelta(days=30)
    else:
        last_date = date.today() - timedelta(days=30)

    # Sync from the day after last sync up to yesterday.
    today = date.today()
    start = last_date + timedelta(days=1)
    end = today - timedelta(days=1)

    if start > end:
        return {"synced": 0, "message": "Already up to date"}

    synced = 0
    errors: list[str] = []

    current = start
    while current <= end:
        try:
            summary = await _fetch_worker("/daily-summary", params={
                "date": current.isoformat(), "days": 1,
            })

            summaries = summary if isinstance(summary, list) else [summary]
            for day_summary in summaries:
                total = day_summary.get("total_qsos", 0)
                if total == 0:
                    current += timedelta(days=1)
                    continue

                # Build markdown document.
                md = _build_daily_markdown(current, day_summary)

                # Chunk and embed.
                chunks = _chunk_text(md)
                for chunk in chunks:
                    try:
                        embedding = await _get_embedding(chunk["text"])
                        vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
                        source_path = f"log-{current.isoformat()}#chunk-{chunk['index']}"
                        meta = json.dumps({
                            "date": current.isoformat(),
                            "chunk_index": chunk["index"],
                            "qso_count": total,
                        })

                        await db.execute(
                            """INSERT INTO elmer.documents
                                (source, source_path, title, content, content_type,
                                 metadata, embedding, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::vector, now())
                            ON CONFLICT (source, source_path)
                                WHERE source IS NOT NULL AND source_path IS NOT NULL
                            DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
                                content_type=EXCLUDED.content_type, metadata=EXCLUDED.metadata,
                                embedding=EXCLUDED.embedding, updated_at=now()""",
                            "log4om-daily",
                            source_path,
                            f"QSO Log Summary for {current.isoformat()}",
                            chunk["text"],
                            "text/markdown",
                            meta,
                            vec_str,
                        )
                    except Exception as exc:
                        errors.append(f"{current}: chunk {chunk['index']}: {exc}")

                synced += 1

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                errors.append(f"{current}: {exc}")
        except Exception as exc:
            errors.append(f"{current}: {exc}")

        current += timedelta(days=1)

    logger.info("Log sync complete: %d days synced, %d errors", synced, len(errors))
    return {"synced": synced, "errors": errors}


def _build_daily_markdown(day: date, summary: dict[str, Any]) -> str:
    """Build a markdown summary document for a single day."""
    lines = [
        f"# QSO Log Summary for {day.isoformat()}",
        "",
        f"W0ABE made **{summary.get('total_qsos', 0)}** contacts on {day.isoformat()}.",
        "",
    ]

    # Unique calls.
    unique = summary.get("unique_calls", 0)
    if unique:
        lines.append(f"Unique callsigns worked: {unique}")

    # Countries.
    countries = summary.get("unique_countries", 0)
    if countries:
        lines.append(f"Countries worked: {countries}")

    # Band breakdown.
    by_band = summary.get("qsos_by_band", {})
    if by_band:
        lines.append("")
        lines.append("## Bands")
        for band, count in sorted(by_band.items()):
            lines.append(f"- {band}: {count} QSOs")

    # Mode breakdown.
    by_mode = summary.get("qsos_by_mode", {})
    if by_mode:
        lines.append("")
        lines.append("## Modes")
        for mode, count in sorted(by_mode.items()):
            lines.append(f"- {mode}: {count} QSOs")

    # Top contacts.
    calls = summary.get("top_calls", [])
    if calls:
        lines.append("")
        lines.append("## Notable Contacts")
        for c in calls[:10]:
            if isinstance(c, dict):
                lines.append(f"- {c.get('call', '?')} ({c.get('country', '?')}, {c.get('band', '?')} {c.get('mode', '?')})")
            else:
                lines.append(f"- {c}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# cross_reference_needs
# ---------------------------------------------------------------------------

async def cross_reference_needs() -> dict[str, Any]:
    """Cross-reference DXCC needs list against worked entities in the log."""
    from .needs_list import get_needs_list

    nl = get_needs_list()
    needs = await nl.get_needs()

    if not needs:
        return {
            "confirmed_worked": [],
            "still_needed": [],
            "total_needs": 0,
            "total_confirmed": 0,
        }

    # Fetch DXCC data from worker.
    dxcc_data = await _fetch_worker("/dxcc")
    dxcc_list = dxcc_data if isinstance(dxcc_data, list) else dxcc_data.get("entities", [])

    # Build lookup: entity name (lowercase) → entity record.
    worked: dict[str, dict] = {}
    for entity in dxcc_list:
        name = entity.get("country", "").lower()
        if name:
            worked[name] = entity

    confirmed_worked: list[dict] = []
    still_needed: list[dict] = []

    for need in needs:
        entity_lower = need.entity.lower()
        # Try exact match or substring match.
        match = worked.get(entity_lower)
        if not match:
            for name, rec in worked.items():
                if entity_lower in name or name in entity_lower:
                    match = rec
                    break

        if match:
            # Check band/mode specifics if specified.
            bands_worked = [b.lower() for b in match.get("bands_worked", [])]
            modes_worked = [m.lower() for m in match.get("modes_worked", [])]

            band_ok = need.band is None or need.band.lower() in bands_worked
            mode_ok = need.mode is None or need.mode.lower() in modes_worked

            if band_ok and mode_ok:
                confirmed_worked.append({
                    "need_id": need.id,
                    "entity": need.entity,
                    "band": need.band,
                    "mode": need.mode,
                    "qso_count": match.get("count", 0),
                    "bands_worked": match.get("bands_worked", []),
                    "modes_worked": match.get("modes_worked", []),
                })
                continue

        still_needed.append({
            "need_id": need.id,
            "entity": need.entity,
            "band": need.band,
            "mode": need.mode,
            "priority": need.priority,
            "notes": need.notes,
        })

    return {
        "confirmed_worked": confirmed_worked,
        "still_needed": still_needed,
        "total_needs": len(needs),
        "total_confirmed": len(confirmed_worked),
    }

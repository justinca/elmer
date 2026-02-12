"""Notes endpoints — Obsidian vault sync, list, search, tags."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..services import db

router = APIRouter(prefix="/notes", tags=["notes"])
logger = logging.getLogger("elmer.notes")

EMBED_TIMEOUT = 60.0
WORKER_TIMEOUT = 30.0


# --- Request / Response models ---


class SyncResultResponse(BaseModel):
    added: int
    updated: int
    deleted: int
    unchanged: int
    errors: int
    duration_seconds: float


class NoteListItem(BaseModel):
    id: int
    source_path: str
    title: str
    tags: list[str] = Field(default_factory=list)
    updated_at: str | None = None
    created_at: str | None = None


class NoteResponse(BaseModel):
    id: int
    source: str | None = None
    source_path: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None
    created_at: str | None = None


class NoteSearchResult(BaseModel):
    id: int
    source_path: str
    title: str
    content: str  # truncated to 500 chars
    tags: list[str] = Field(default_factory=list)
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class TagListResponse(BaseModel):
    tags: list[str]
    count: int


# --- Helpers ---


async def _get_embedding(text: str) -> list[float]:
    """Generate embedding via worker, falling back to Ollama direct."""
    if len(text) > 32000:
        text = text[:32000]

    payload = {"model": "nomic-embed-text", "input": text}
    worker_url = f"{settings.worker_base_url}/llm/embed"
    ollama_url = f"{settings.ollama_base_url}/api/embed"

    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        try:
            resp = await client.post(worker_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker embed failed (%s), falling back to Ollama", exc)

    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        try:
            resp = await client.post(ollama_url, json=payload)
            resp.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Embedding timed out")
        except httpx.ConnectError:
            raise HTTPException(
                status_code=502, detail="Cannot reach Ollama for embeddings"
            )

    data = resp.json()
    embeddings = data.get("embeddings", [])
    if not embeddings:
        raise HTTPException(status_code=502, detail="No embeddings returned")
    return embeddings[0]


async def _publish_mqtt(data: dict) -> None:
    """Publish sync results to MQTT (best-effort)."""
    try:
        import aiomqtt

        async with aiomqtt.Client(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USER or None,
            password=settings.MQTT_PASSWORD or None,
            identifier="elmer-core-notes",
        ) as client:
            payload = json.dumps(data, default=str)
            await client.publish("elmer/knowledge/obsidian/sync", payload)
    except Exception:
        logger.warning("Failed to publish MQTT notification (non-fatal)")


def _parse_metadata(raw: Any) -> dict:
    """Parse metadata from DB row (may be str or dict)."""
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or {}


# --- Sync implementation ---


async def _sync_notes(full: bool = True) -> SyncResultResponse:
    """Core implementation of vault sync.

    Calls the worker API for vault file access, embeds content, and
    upserts into elmer.notes.
    """
    start_time = time.monotonic()
    added = updated = deleted = unchanged = errors = 0
    worker_base = settings.worker_base_url

    if full:
        # Fetch all notes from worker.
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            try:
                resp = await client.get(f"{worker_base}/obsidian/notes")
                resp.raise_for_status()
                vault_notes = resp.json()
            except httpx.ConnectError:
                raise HTTPException(
                    status_code=502,
                    detail="Cannot reach worker — is it running?",
                )
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Worker returned HTTP {exc.response.status_code}",
                )

        vault_paths = {n["path"] for n in vault_notes}

        # Get existing DB notes.
        db_rows = await db.fetch_all(
            "SELECT source_path, updated_at FROM elmer.notes WHERE source = 'obsidian'"
        )
        db_map = {row["source_path"]: row["updated_at"] for row in db_rows}

    else:
        # Incremental: get last sync time.
        last_row = await db.fetch_one(
            """
            SELECT timestamp FROM elmer.events
            WHERE source = 'obsidian_sync'
              AND event_type IN ('full_sync', 'incremental_sync')
            ORDER BY timestamp DESC LIMIT 1
            """
        )
        if last_row is None:
            return await _sync_notes(full=True)

        since = last_row["timestamp"]
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            try:
                resp = await client.get(
                    f"{worker_base}/obsidian/notes/changed",
                    params={"since": since.isoformat()},
                )
                resp.raise_for_status()
                vault_notes = resp.json()
            except httpx.ConnectError:
                raise HTTPException(
                    status_code=502,
                    detail="Cannot reach worker — is it running?",
                )
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Worker returned HTTP {exc.response.status_code}",
                )

        vault_paths = None  # Incremental doesn't detect deletions.
        db_map = {}
        for note_info in vault_notes:
            row = await db.fetch_one(
                "SELECT source_path, updated_at FROM elmer.notes "
                "WHERE source = 'obsidian' AND source_path = $1",
                note_info["path"],
            )
            if row:
                db_map[row["source_path"]] = row["updated_at"]

    # Process notes.
    for note_info in vault_notes:
        path = note_info["path"]
        modified_at = datetime.fromisoformat(note_info["modified_at"])

        # Skip unchanged (full sync only uses this effectively).
        if path in db_map and db_map[path] is not None:
            db_ts = db_map[path]
            if db_ts.tzinfo is None:
                db_ts = db_ts.replace(tzinfo=timezone.utc)
            if db_ts >= modified_at:
                unchanged += 1
                continue

        try:
            # Fetch full note content.
            async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
                resp = await client.get(
                    f"{worker_base}/obsidian/note",
                    params={"path": path},
                )
                resp.raise_for_status()
                note = resp.json()

            content = note["content"]
            title = note.get("title", "")
            tags = note.get("tags", [])
            frontmatter = note.get("frontmatter", {})
            links = note.get("links", [])

            # Generate embedding.
            embedding = await _get_embedding(content)
            vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

            metadata = json.dumps(
                {
                    "frontmatter": frontmatter,
                    "links": links,
                    "modified_at": modified_at.isoformat(),
                },
                default=str,
            )

            # Upsert note.
            await db.execute(
                """
                INSERT INTO elmer.notes
                    (source, source_path, title, content, tags, embedding, metadata, updated_at)
                VALUES ('obsidian', $1, $2, $3, $4, $5::vector, $6::jsonb, $7)
                ON CONFLICT (source_path)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    tags = EXCLUDED.tags,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                path, title, content, tags, vec_str, metadata, modified_at,
            )

            if path in db_map:
                updated += 1
            else:
                added += 1

        except HTTPException:
            raise
        except Exception:
            logger.exception("Failed to sync note: %s", path)
            errors += 1

    # Delete removed notes (full sync only).
    if full and vault_paths is not None:
        for db_path in db_map:
            if db_path not in vault_paths:
                await db.execute(
                    "DELETE FROM elmer.notes "
                    "WHERE source = 'obsidian' AND source_path = $1",
                    db_path,
                )
                deleted += 1

    duration = round(time.monotonic() - start_time, 2)
    event_type = "full_sync" if full else "incremental_sync"

    # Record sync event.
    event_data = json.dumps(
        {
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "unchanged": unchanged,
            "errors": errors,
            "duration_seconds": duration,
        }
    )
    try:
        await db.execute(
            "INSERT INTO elmer.events (source, event_type, data) "
            "VALUES ($1, $2, $3::jsonb)",
            "obsidian_sync", event_type, event_data,
        )
    except Exception:
        logger.warning("Failed to record sync event")

    result = SyncResultResponse(
        added=added,
        updated=updated,
        deleted=deleted,
        unchanged=unchanged,
        errors=errors,
        duration_seconds=duration,
    )

    # Publish MQTT notification.
    await _publish_mqtt(
        {
            "event": event_type,
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "unchanged": unchanged,
            "errors": errors,
            "duration_seconds": duration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    logger.info(
        "%s complete: +%d ~%d -%d =%d err=%d (%.1fs)",
        event_type, added, updated, deleted, unchanged, errors, duration,
    )
    return result


# --- Endpoints ---
# NOTE: /search, /tags, /tag/{tag} must come BEFORE /{note_id} to avoid
# FastAPI matching those paths as integer IDs.


@router.post("/sync", response_model=SyncResultResponse)
async def trigger_full_sync():
    """Trigger a full Obsidian vault sync.

    Fetches all notes from the worker, compares with DB, upserts changed
    notes with embeddings, and deletes notes no longer in the vault.
    """
    return await _sync_notes(full=True)


@router.post("/sync/incremental", response_model=SyncResultResponse)
async def trigger_incremental_sync():
    """Trigger an incremental sync (only notes changed since last sync)."""
    return await _sync_notes(full=False)


@router.get("", response_model=list[NoteListItem])
async def list_notes(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List all synced notes, most recently updated first."""
    rows = await db.fetch_all(
        """
        SELECT id, source_path, title, tags, updated_at, created_at
        FROM elmer.notes
        WHERE source = 'obsidian'
        ORDER BY updated_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )
    return [
        NoteListItem(
            id=r["id"],
            source_path=r["source_path"] or "",
            title=r["title"] or "",
            tags=r["tags"] or [],
            updated_at=str(r["updated_at"]) if r["updated_at"] else None,
            created_at=str(r["created_at"]) if r["created_at"] else None,
        )
        for r in rows
    ]


@router.get("/search", response_model=list[NoteSearchResult])
async def search_notes(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=5, le=50),
):
    """Semantic search over note embeddings."""
    embedding = await _get_embedding(q)
    vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

    rows = await db.fetch_all(
        """
        SELECT id, source_path, title, content, tags, metadata,
               1 - (embedding <=> $1::vector) AS score
        FROM elmer.notes
        WHERE embedding IS NOT NULL
          AND 1 - (embedding <=> $1::vector) >= 0.5
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        vec_str, limit,
    )
    return [
        NoteSearchResult(
            id=r["id"],
            source_path=r["source_path"] or "",
            title=r["title"] or "",
            content=(r["content"] or "")[:500],
            tags=r["tags"] or [],
            score=float(r["score"]),
            metadata=_parse_metadata(r["metadata"]),
        )
        for r in rows
    ]


@router.get("/tags", response_model=TagListResponse)
async def list_tags():
    """List all unique tags across synced notes."""
    rows = await db.fetch_all(
        """
        SELECT DISTINCT unnest(tags) AS tag
        FROM elmer.notes
        WHERE source = 'obsidian' AND tags IS NOT NULL
        ORDER BY tag
        """
    )
    tags = [r["tag"] for r in rows]
    return TagListResponse(tags=tags, count=len(tags))


@router.get("/tag/{tag}", response_model=list[NoteListItem])
async def list_notes_by_tag(tag: str):
    """List all notes containing a specific tag."""
    rows = await db.fetch_all(
        """
        SELECT id, source_path, title, tags, updated_at, created_at
        FROM elmer.notes
        WHERE source = 'obsidian' AND $1 = ANY(tags)
        ORDER BY updated_at DESC
        """,
        tag,
    )
    return [
        NoteListItem(
            id=r["id"],
            source_path=r["source_path"] or "",
            title=r["title"] or "",
            tags=r["tags"] or [],
            updated_at=str(r["updated_at"]) if r["updated_at"] else None,
            created_at=str(r["created_at"]) if r["created_at"] else None,
        )
        for r in rows
    ]


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(note_id: int):
    """Get a single note with full content."""
    row = await db.fetch_one(
        """
        SELECT id, source, source_path, title, content, tags,
               metadata, updated_at, created_at
        FROM elmer.notes WHERE id = $1
        """,
        note_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")

    return NoteResponse(
        id=row["id"],
        source=row["source"],
        source_path=row["source_path"] or "",
        title=row["title"] or "",
        content=row["content"] or "",
        tags=row["tags"] or [],
        metadata=_parse_metadata(row["metadata"]),
        updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )

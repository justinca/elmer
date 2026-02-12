"""Obsidian vault sync — fetches notes from worker, embeds, stores in PostgreSQL."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx

from .config import settings

logger = logging.getLogger("elmer.knowledge.obsidian_sync")

EMBED_TIMEOUT = 60.0
WORKER_TIMEOUT = 30.0


@dataclass
class SyncResult:
    """Results of a sync operation."""

    added: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    errors: int = 0
    duration_seconds: float = 0.0


class ObsidianSync:
    """Syncs Obsidian vault notes to elmer.notes via the worker API."""

    def __init__(self, pool: asyncpg.Pool | None = None):
        self._pool = pool

    async def connect_db(self) -> None:
        """Create a connection pool if one wasn't provided."""
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            min_size=2,
            max_size=5,
        )
        logger.info("ObsidianSync connected to PostgreSQL")

    async def close_db(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Not connected — call connect_db() first")
        return self._pool

    # ------------------------------------------------------------------
    # Full sync
    # ------------------------------------------------------------------

    async def full_sync(self) -> SyncResult:
        """Full sync: fetch all notes, compare timestamps, upsert/delete."""
        start = time.monotonic()
        result = SyncResult()
        pool = self._require_pool()

        # 1. Fetch note list from worker.
        vault_notes = await self._fetch_all_notes()
        vault_paths = {n["path"] for n in vault_notes}
        logger.info("Worker reports %d notes in vault", len(vault_notes))

        # 2. Get existing DB notes.
        db_rows = await pool.fetch(
            "SELECT source_path, updated_at FROM elmer.notes WHERE source = 'obsidian'"
        )
        db_map = {row["source_path"]: row["updated_at"] for row in db_rows}

        # 3. Process each vault note.
        for note_info in vault_notes:
            path = note_info["path"]
            modified_at = datetime.fromisoformat(note_info["modified_at"])

            # Skip unchanged.
            if path in db_map and db_map[path] is not None:
                db_ts = db_map[path]
                if db_ts.tzinfo is None:
                    db_ts = db_ts.replace(tzinfo=timezone.utc)
                if db_ts >= modified_at:
                    result.unchanged += 1
                    continue

            try:
                note = await self._fetch_note_content(path)
                await self._upsert_note(note, modified_at)
                if path in db_map:
                    result.updated += 1
                else:
                    result.added += 1
            except Exception:
                logger.exception("Failed to sync note: %s", path)
                result.errors += 1

        # 4. Delete notes no longer in vault.
        for db_path in db_map:
            if db_path not in vault_paths:
                await pool.execute(
                    "DELETE FROM elmer.notes WHERE source = 'obsidian' AND source_path = $1",
                    db_path,
                )
                result.deleted += 1

        result.duration_seconds = round(time.monotonic() - start, 2)

        # 5. Record sync event.
        await self._record_sync_event("full_sync", result)

        logger.info(
            "Full sync complete: +%d ~%d -%d =%d err=%d (%.1fs)",
            result.added, result.updated, result.deleted,
            result.unchanged, result.errors, result.duration_seconds,
        )
        return result

    # ------------------------------------------------------------------
    # Incremental sync
    # ------------------------------------------------------------------

    async def incremental_sync(self) -> SyncResult:
        """Incremental sync: only notes changed since last sync."""
        start = time.monotonic()
        result = SyncResult()
        pool = self._require_pool()

        # Get last sync timestamp from events.
        last_sync = await self._get_last_sync_time()
        if last_sync is None:
            logger.info("No previous sync found, running full sync")
            return await self.full_sync()

        since_str = last_sync.isoformat()
        logger.info("Incremental sync since %s", since_str)

        # Fetch changed notes from worker.
        changed_notes = await self._fetch_changed_notes(since_str)
        logger.info("Worker reports %d changed notes", len(changed_notes))

        for note_info in changed_notes:
            path = note_info["path"]
            modified_at = datetime.fromisoformat(note_info["modified_at"])
            try:
                existing = await pool.fetchrow(
                    "SELECT id FROM elmer.notes WHERE source = 'obsidian' AND source_path = $1",
                    path,
                )
                note = await self._fetch_note_content(path)
                await self._upsert_note(note, modified_at)
                if existing:
                    result.updated += 1
                else:
                    result.added += 1
            except Exception:
                logger.exception("Failed to sync note: %s", path)
                result.errors += 1

        result.duration_seconds = round(time.monotonic() - start, 2)
        await self._record_sync_event("incremental_sync", result)

        logger.info(
            "Incremental sync complete: +%d ~%d err=%d (%.1fs)",
            result.added, result.updated, result.errors, result.duration_seconds,
        )
        return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_notes(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Semantic search over synced note embeddings."""
        pool = self._require_pool()
        embedding = await self._get_embedding(query)
        vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

        rows = await pool.fetch(
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
            {
                "id": r["id"],
                "source_path": r["source_path"],
                "title": r["title"],
                "content": (r["content"] or "")[:500],
                "tags": r["tags"] or [],
                "score": float(r["score"]),
                "metadata": (
                    json.loads(r["metadata"])
                    if isinstance(r["metadata"], str)
                    else (r["metadata"] or {})
                ),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # MQTT notification
    # ------------------------------------------------------------------

    async def publish_mqtt(self, result: SyncResult) -> None:
        """Publish sync result to MQTT topic elmer/knowledge/obsidian/sync."""
        try:
            import aiomqtt

            async with aiomqtt.Client(
                hostname=settings.MQTT_HOST,
                port=settings.MQTT_PORT,
                username=settings.MQTT_USER or None,
                password=settings.MQTT_PASSWORD or None,
                identifier="elmer-knowledge-obsidian",
            ) as client:
                payload = json.dumps(
                    {
                        "added": result.added,
                        "updated": result.updated,
                        "deleted": result.deleted,
                        "unchanged": result.unchanged,
                        "errors": result.errors,
                        "duration_seconds": result.duration_seconds,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    default=str,
                )
                await client.publish("elmer/knowledge/obsidian/sync", payload)
                logger.info("Published sync result to MQTT")
        except Exception:
            logger.warning("Failed to publish MQTT notification (non-fatal)")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding via worker, falling back to Ollama direct."""
        # Truncate very long texts (nomic-embed-text handles ~8192 tokens).
        if len(text) > 32000:
            text = text[:32000]

        payload = {"model": settings.EMBEDDING_MODEL, "input": text}

        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
            try:
                resp = await client.post(settings.worker_embed_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if embeddings:
                    return embeddings[0]
            except (httpx.RequestError, RuntimeError) as exc:
                logger.warning("Worker embed failed (%s), trying Ollama direct", exc)

        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
            resp = await client.post(settings.ollama_embed_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise RuntimeError("No embeddings returned")
            return embeddings[0]

    async def _fetch_all_notes(self) -> list[dict]:
        """GET /obsidian/notes from worker."""
        url = f"{settings.worker_base_url}/obsidian/notes"
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def _fetch_changed_notes(self, since: str) -> list[dict]:
        """GET /obsidian/notes/changed?since=... from worker."""
        url = f"{settings.worker_base_url}/obsidian/notes/changed"
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            resp = await client.get(url, params={"since": since})
            resp.raise_for_status()
            return resp.json()

    async def _fetch_note_content(self, path: str) -> dict:
        """GET /obsidian/note?path=... from worker."""
        url = f"{settings.worker_base_url}/obsidian/note"
        async with httpx.AsyncClient(timeout=WORKER_TIMEOUT) as client:
            resp = await client.get(url, params={"path": path})
            resp.raise_for_status()
            return resp.json()

    async def _upsert_note(self, note: dict, modified_at: datetime) -> None:
        """Insert or update a note in elmer.notes with embedding."""
        pool = self._require_pool()
        content = note["content"]
        title = note.get("title", "")
        tags = note.get("tags", [])
        path = note["path"]
        frontmatter = note.get("frontmatter", {})
        links = note.get("links", [])

        # Generate embedding.
        embedding = await self._get_embedding(content)
        vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

        metadata = json.dumps(
            {
                "frontmatter": frontmatter,
                "links": links,
                "modified_at": modified_at.isoformat(),
            },
            default=str,
        )

        await pool.execute(
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

    async def _get_last_sync_time(self) -> datetime | None:
        """Get the timestamp of the last successful sync from elmer.events."""
        pool = self._require_pool()
        row = await pool.fetchrow(
            """
            SELECT timestamp FROM elmer.events
            WHERE source = 'obsidian_sync'
              AND event_type IN ('full_sync', 'incremental_sync')
            ORDER BY timestamp DESC
            LIMIT 1
            """
        )
        if row is None:
            return None
        ts = row["timestamp"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts

    async def _record_sync_event(self, event_type: str, result: SyncResult) -> None:
        """Record sync result in elmer.events."""
        pool = self._require_pool()
        data = json.dumps(
            {
                "added": result.added,
                "updated": result.updated,
                "deleted": result.deleted,
                "unchanged": result.unchanged,
                "errors": result.errors,
                "duration_seconds": result.duration_seconds,
            }
        )
        try:
            await pool.execute(
                "INSERT INTO elmer.events (source, event_type, data) VALUES ($1, $2, $3::jsonb)",
                "obsidian_sync", event_type, data,
            )
        except Exception:
            logger.warning("Failed to record sync event (non-fatal)")

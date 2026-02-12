"""Transcription pipeline — sends audio to the worker, stores results, embeds for RAG."""

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from .config import settings
from .models import TranscriptionResult, TranscriptionSegment, TranscriptionListItem

logger = logging.getLogger("elmer.transcription.pipeline")

# Timeout for transcription — 2-hour audio can take a while.
TRANSCRIBE_TIMEOUT = 600.0  # 10 minutes
EMBED_TIMEOUT = 60.0
# Retry settings for worker unavailability.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5.0  # seconds, doubles each retry

# Audio MIME types for streaming upload.
_MIME_MAP = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}


class TranscriptionPipeline:
    """Orchestrates transcription, storage, embedding, and MQTT notification."""

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
        logger.info("Pipeline connected to PostgreSQL")

    async def close_db(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    async def transcribe_file(
        self,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        """Full pipeline: upload → transcribe → store → embed → notify.

        Args:
            file_path: Path to the audio file on disk.
            metadata: Optional metadata dict to store with the transcription.

        Returns:
            TranscriptionResult with id, text, segments, duration.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        file_size = path.stat().st_size
        logger.info("Starting transcription of %s (%.1f MB)", path.name, file_size / 1e6)

        # 1. Send to worker for transcription (with retry).
        worker_result = await self._send_to_worker(path)

        # 2. Store in PostgreSQL.
        row_id = await self._store_transcription(path.name, worker_result, metadata)

        # 3. Generate embedding and update the row.
        transcript_text = worker_result.get("transcript", "")
        if transcript_text.strip():
            await self._embed_and_store(row_id, transcript_text)

        # 4. Publish MQTT notification.
        await self._publish_result(row_id, path.name, worker_result)

        # 5. Build and return result.
        segments = [
            TranscriptionSegment(**s) for s in worker_result.get("segments", [])
        ]
        return TranscriptionResult(
            id=row_id,
            audio_file=path.name,
            transcript=transcript_text,
            segments=segments,
            language=worker_result.get("language"),
            duration_seconds=worker_result.get("duration_seconds"),
            model=worker_result.get("model"),
            metadata=metadata or {},
        )

    async def transcribe_url(self, url: str, metadata: dict[str, Any] | None = None) -> TranscriptionResult:
        """Download audio from a URL, then transcribe it."""
        logger.info("Downloading audio from %s", url)
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        # Guess extension from URL or content-type.
        url_path = url.split("?")[0]
        suffix = Path(url_path).suffix or ".wav"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        try:
            meta = dict(metadata or {})
            meta["source_url"] = url
            return await self.transcribe_file(tmp_path, metadata=meta)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    async def list_transcriptions(self, limit: int = 50, offset: int = 0) -> list[TranscriptionListItem]:
        """List transcriptions, most recent first."""
        pool = self._require_pool()
        rows = await pool.fetch(
            """
            SELECT id, audio_file, transcript, language, duration_seconds, model, created_at
            FROM elmer.transcriptions
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )
        return [
            TranscriptionListItem(
                id=r["id"],
                audio_file=r["audio_file"] or "",
                transcript=r["transcript"] or "",
                language=r["language"],
                duration_seconds=r["duration_seconds"],
                model=r["model"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def get_transcription(self, transcription_id: int) -> TranscriptionResult | None:
        """Get a single transcription by ID."""
        pool = self._require_pool()
        row = await pool.fetchrow(
            """
            SELECT id, audio_file, transcript, segments, language,
                   duration_seconds, model, metadata, created_at
            FROM elmer.transcriptions WHERE id = $1
            """,
            transcription_id,
        )
        if row is None:
            return None

        raw_segments = row["segments"]
        if isinstance(raw_segments, str):
            raw_segments = json.loads(raw_segments)
        segments = [TranscriptionSegment(**s) for s in (raw_segments or [])]

        raw_meta = row["metadata"]
        if isinstance(raw_meta, str):
            raw_meta = json.loads(raw_meta)

        return TranscriptionResult(
            id=row["id"],
            audio_file=row["audio_file"] or "",
            transcript=row["transcript"] or "",
            segments=segments,
            language=row["language"],
            duration_seconds=row["duration_seconds"],
            model=row["model"],
            metadata=raw_meta or {},
            created_at=row["created_at"],
        )

    async def search_transcriptions(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Semantic search over transcription embeddings."""
        pool = self._require_pool()
        embedding = await self._get_embedding(query)
        vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

        rows = await pool.fetch(
            """
            SELECT id, audio_file, transcript, metadata,
                   1 - (embedding <=> $1::vector) AS score
            FROM elmer.transcriptions
            WHERE embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) >= 0.5
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            vec_str, limit,
        )
        results = []
        for r in rows:
            raw_meta = r["metadata"]
            if isinstance(raw_meta, str):
                raw_meta = json.loads(raw_meta)
            results.append({
                "id": r["id"],
                "audio_file": r["audio_file"],
                "transcript": r["transcript"][:500] if r["transcript"] else "",
                "score": float(r["score"]),
                "metadata": raw_meta or {},
            })
        return results

    async def delete_transcription(self, transcription_id: int) -> bool:
        """Delete a transcription by ID. Returns True if a row was deleted."""
        pool = self._require_pool()
        result = await pool.execute(
            "DELETE FROM elmer.transcriptions WHERE id = $1", transcription_id
        )
        return result == "DELETE 1"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Pipeline not connected — call connect_db() first")
        return self._pool

    async def _send_to_worker(self, path: Path) -> dict[str, Any]:
        """Upload audio to the worker with retry and backoff."""
        mime = _MIME_MAP.get(path.suffix.lower(), "application/octet-stream")
        delay = RETRY_BASE_DELAY

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT) as client:
                    with open(path, "rb") as f:
                        resp = await client.post(
                            settings.worker_transcribe_url,
                            files={"file": (path.name, f, mime)},
                        )
                    resp.raise_for_status()
                    data = resp.json()

                if data.get("status") == "success":
                    return data

                raise RuntimeError(f"Worker returned status={data.get('status')}: {data.get('message', '')}")

            except httpx.TimeoutException:
                logger.warning(
                    "Transcription timeout (attempt %d/%d, %.0fs limit)",
                    attempt, MAX_RETRIES, TRANSCRIBE_TIMEOUT,
                )
            except httpx.ConnectError as exc:
                logger.warning(
                    "Worker unreachable (attempt %d/%d): %s", attempt, MAX_RETRIES, exc,
                )
            except RuntimeError:
                raise  # Don't retry application errors.
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Worker returned %d (attempt %d/%d): %s",
                    exc.response.status_code, attempt, MAX_RETRIES, exc,
                )

            if attempt < MAX_RETRIES:
                logger.info("Retrying in %.0fs...", delay)
                await asyncio.sleep(delay)
                delay *= 2

        raise RuntimeError(
            f"Transcription failed after {MAX_RETRIES} attempts — "
            f"worker at {settings.worker_transcribe_url} may be down"
        )

    async def _store_transcription(
        self,
        filename: str,
        worker_result: dict[str, Any],
        metadata: dict[str, Any] | None,
    ) -> int:
        """Insert transcription into elmer.transcriptions, return row ID."""
        pool = self._require_pool()
        segments_json = json.dumps(worker_result.get("segments", []))
        meta_json = json.dumps(metadata or {})

        row = await pool.fetchrow(
            """
            INSERT INTO elmer.transcriptions
                (audio_file, transcript, segments, language, duration_seconds, model, metadata)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7::jsonb)
            RETURNING id
            """,
            filename,
            worker_result.get("transcript", ""),
            segments_json,
            worker_result.get("language"),
            worker_result.get("duration_seconds"),
            worker_result.get("model"),
            meta_json,
        )
        row_id = row["id"]
        logger.info("Stored transcription id=%d for %s", row_id, filename)
        return row_id

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate an embedding via worker, falling back to Ollama direct."""
        payload = {"model": settings.EMBEDDING_MODEL, "input": text}

        # Try worker first.
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

        # Fallback to Ollama directly.
        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
            resp = await client.post(settings.ollama_embed_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise RuntimeError("No embeddings returned from Ollama")
            return embeddings[0]

    async def _embed_and_store(self, row_id: int, transcript: str) -> None:
        """Generate an embedding for the transcript and store it."""
        try:
            embedding = await self._get_embedding(transcript)
            vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
            pool = self._require_pool()
            await pool.execute(
                "UPDATE elmer.transcriptions SET embedding = $1::vector WHERE id = $2",
                vec_str, row_id,
            )
            logger.info("Stored embedding for transcription id=%d (%d dims)", row_id, len(embedding))
        except Exception:
            logger.exception("Failed to generate/store embedding for transcription id=%d", row_id)

    async def _publish_result(
        self, row_id: int, filename: str, worker_result: dict[str, Any],
    ) -> None:
        """Publish transcription result to MQTT."""
        try:
            import aiomqtt

            async with aiomqtt.Client(
                hostname=settings.MQTT_HOST,
                port=settings.MQTT_PORT,
                username=settings.MQTT_USER or None,
                password=settings.MQTT_PASSWORD or None,
                identifier="elmer-transcription-pipeline",
            ) as client:
                payload = json.dumps({
                    "id": row_id,
                    "audio_file": filename,
                    "transcript": worker_result.get("transcript", "")[:500],
                    "language": worker_result.get("language"),
                    "duration_seconds": worker_result.get("duration_seconds"),
                    "model": worker_result.get("model"),
                    "segments_count": len(worker_result.get("segments", [])),
                }, default=str)
                await client.publish("elmer/transcription/result", payload)
                logger.info("Published MQTT notification for transcription id=%d", row_id)
        except Exception:
            logger.warning("Failed to publish MQTT notification (non-fatal)")

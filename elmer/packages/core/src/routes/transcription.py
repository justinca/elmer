"""Transcription endpoints — upload, list, get, search, delete."""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..config import settings
from ..services import db

router = APIRouter(prefix="/transcription", tags=["transcription"])
logger = logging.getLogger("elmer.transcription")

# Worker transcription timeout — large files can take a long time.
TRANSCRIBE_TIMEOUT = 600.0
EMBED_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)


# --- Request / Response models ---


class TranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptionResponse(BaseModel):
    id: int
    audio_file: str
    transcript: str
    segments: list[TranscriptionSegment] = Field(default_factory=list)
    language: str | None = None
    duration_seconds: float | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class TranscriptionListItem(BaseModel):
    id: int
    audio_file: str
    transcript: str
    language: str | None = None
    duration_seconds: float | None = None
    model: str | None = None
    created_at: str | None = None


class TranscriptionSearchResult(BaseModel):
    id: int
    audio_file: str
    transcript: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Helpers ---


async def _get_embedding(text: str) -> list[float]:
    """Generate an embedding via worker, falling back to Ollama direct."""
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
            raise HTTPException(status_code=502, detail="Cannot reach Ollama for embeddings")

    data = resp.json()
    embeddings = data.get("embeddings", [])
    if not embeddings:
        raise HTTPException(status_code=502, detail="No embeddings returned")
    return embeddings[0]


async def _publish_mqtt(row_id: int, filename: str, worker_result: dict[str, Any]) -> None:
    """Publish transcription result to MQTT (best-effort)."""
    try:
        import aiomqtt

        async with aiomqtt.Client(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USER or None,
            password=settings.MQTT_PASSWORD or None,
            identifier="elmer-core-transcription",
        ) as client:
            payload = json.dumps({
                "id": row_id,
                "audio_file": filename,
                "transcript": worker_result.get("transcript", "")[:500],
                "language": worker_result.get("language"),
                "duration_seconds": worker_result.get("duration_seconds"),
            }, default=str)
            await client.publish("elmer/transcription/result", payload)
    except Exception:
        logger.warning("Failed to publish MQTT notification (non-fatal)")


# --- Endpoints ---


@router.post("/upload", response_model=TranscriptionResponse)
async def upload_and_transcribe(file: UploadFile = File(...)):
    """Upload an audio file and transcribe it via the worker.

    Full pipeline: upload → worker transcription → store in DB → embed → MQTT notify.
    """
    suffix = Path(file.filename).suffix if file.filename else ".wav"

    # Save upload to temp file.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)

    try:
        # Send to worker.
        mime_map = {
            ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
            ".flac": "audio/flac", ".ogg": "audio/ogg", ".webm": "audio/webm",
        }
        mime = mime_map.get(suffix.lower(), "application/octet-stream")

        try:
            async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT) as client:
                with open(tmp_path, "rb") as f:
                    resp = await client.post(
                        f"{settings.worker_base_url}/transcribe",
                        files={"file": (file.filename or "audio" + suffix, f, mime)},
                    )
                resp.raise_for_status()
                worker_data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Transcription timed out — the audio may be too long or the worker overloaded",
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=502,
                detail=f"Cannot reach worker at {settings.worker_base_url} — is it running?",
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500]
            logger.error("Worker transcription failed (HTTP %d): %s",
                         exc.response.status_code, body)
            raise HTTPException(
                status_code=502,
                detail=f"Worker error (HTTP {exc.response.status_code}): {body}",
            )

        # Worker returns {text, segments, language, duration};
        # normalise to the field names Core uses internally.
        transcript_text = worker_data.get("text") or worker_data.get("transcript") or ""
        duration_secs = worker_data.get("duration") or worker_data.get("duration_seconds")

        if not transcript_text and not worker_data.get("segments"):
            raise HTTPException(
                status_code=502,
                detail=f"Worker error: {worker_data.get('message', worker_data.get('detail', 'empty response'))}",
            )

        # Store in database.
        segments_json = json.dumps(worker_data.get("segments", []))
        meta_json = json.dumps({"source": "api_upload", "original_filename": file.filename})

        row = await db.fetch_one(
            """
            INSERT INTO elmer.transcriptions
                (audio_file, transcript, segments, language, duration_seconds, model, metadata)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7::jsonb)
            RETURNING id, created_at
            """,
            file.filename or "upload" + suffix,
            transcript_text,
            segments_json,
            worker_data.get("language"),
            duration_secs,
            worker_data.get("model"),
            meta_json,
        )
        row_id = row["id"]

        # Generate and store embedding (non-blocking on failure).
        if transcript_text.strip():
            try:
                embedding = await _get_embedding(transcript_text)
                vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
                await db.execute(
                    "UPDATE elmer.transcriptions SET embedding = $1::vector WHERE id = $2",
                    vec_str, row_id,
                )
            except Exception:
                logger.exception("Failed to embed transcription id=%d", row_id)

        # Publish MQTT notification.
        await _publish_mqtt(row_id, file.filename or "", worker_data)

        segments = [TranscriptionSegment(**s) for s in worker_data.get("segments", [])]
        return TranscriptionResponse(
            id=row_id,
            audio_file=file.filename or "",
            transcript=transcript_text,
            segments=segments,
            language=worker_data.get("language"),
            duration_seconds=duration_secs,
            model=worker_data.get("model"),
            metadata={"source": "api_upload", "original_filename": file.filename},
            created_at=str(row["created_at"]),
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("", response_model=list[TranscriptionListItem])
async def list_transcriptions(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List all transcriptions, most recent first."""
    rows = await db.fetch_all(
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
            transcript=(r["transcript"] or "")[:500],
            language=r["language"],
            duration_seconds=r["duration_seconds"],
            model=r["model"],
            created_at=str(r["created_at"]) if r["created_at"] else None,
        )
        for r in rows
    ]


@router.get("/search", response_model=list[TranscriptionSearchResult])
async def search_transcriptions(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=5, le=50),
):
    """Semantic search over transcription embeddings."""
    embedding = await _get_embedding(q)
    vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

    rows = await db.fetch_all(
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
    return [
        TranscriptionSearchResult(
            id=r["id"],
            audio_file=r["audio_file"] or "",
            transcript=(r["transcript"] or "")[:500],
            score=float(r["score"]),
            metadata=json.loads(r["metadata"]) if r["metadata"] else {},
        )
        for r in rows
    ]


@router.get("/{transcription_id}", response_model=TranscriptionResponse)
async def get_transcription(transcription_id: int):
    """Get a single transcription with full segments."""
    row = await db.fetch_one(
        """
        SELECT id, audio_file, transcript, segments, language,
               duration_seconds, model, metadata, created_at
        FROM elmer.transcriptions WHERE id = $1
        """,
        transcription_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Transcription not found")

    raw_segments = row["segments"]
    if isinstance(raw_segments, str):
        raw_segments = json.loads(raw_segments)

    raw_meta = row["metadata"]
    if isinstance(raw_meta, str):
        raw_meta = json.loads(raw_meta)

    return TranscriptionResponse(
        id=row["id"],
        audio_file=row["audio_file"] or "",
        transcript=row["transcript"] or "",
        segments=[TranscriptionSegment(**s) for s in (raw_segments or [])],
        language=row["language"],
        duration_seconds=row["duration_seconds"],
        model=row["model"],
        metadata=raw_meta or {},
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )


@router.delete("/{transcription_id}")
async def delete_transcription(transcription_id: int):
    """Delete a transcription by ID."""
    result = await db.execute(
        "DELETE FROM elmer.transcriptions WHERE id = $1", transcription_id
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Transcription not found")
    return {"status": "deleted", "id": transcription_id}

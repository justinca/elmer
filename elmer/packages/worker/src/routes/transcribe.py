"""Whisper transcription endpoints.

Accepts audio file uploads or local file paths and returns structured
transcription results using faster-whisper (CTranslate2 backend).
Optionally runs speaker diarization via pyannote.audio.
"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from ..services import gpu_monitor, whisper_service, diarize_service

logger = logging.getLogger("elmer.worker.transcribe")
router = APIRouter()

TRANSCRIBE_TIMEOUT = 300  # 5 minutes for transcription only
DIARIZE_TIMEOUT = 600     # 10 minutes when diarization is included


class FilePathRequest(BaseModel):
    """Request body for transcribing a file already on disk."""
    path: str
    diarize: bool = False


@router.post("")
async def transcribe_upload(
    file: UploadFile = File(...),
    diarize: bool = Query(False, description="Enable speaker diarization"),
):
    """Transcribe an uploaded audio file.

    Accepts multipart file upload. Supported formats: wav, mp3, m4a, flac, ogg.
    Pass ?diarize=true to add speaker labels to segments.

    Returns transcription with text, segments, language, and duration.
    """
    filename = file.filename or "audio.wav"
    suffix = Path(filename).suffix.lower()

    if suffix not in whisper_service.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{suffix}'. Supported: {', '.join(whisper_service.SUPPORTED_EXTENSIONS)}",
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    timeout = DIARIZE_TIMEOUT if diarize else TRANSCRIBE_TIMEOUT
    logger.info("Transcribe upload: %s (%d bytes, diarize=%s)", filename, len(audio_bytes), diarize)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                whisper_service.transcribe_bytes, audio_bytes, suffix=suffix, diarize=diarize,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Transcription timed out after {timeout}s")
    except Exception as exc:
        logger.exception("Transcription failed for %s", filename)
        raise HTTPException(status_code=500, detail=f"Transcription error: {exc}")
    return result


@router.post("/file")
async def transcribe_file(req: FilePathRequest):
    """Transcribe a file already present on this Windows machine.

    Accepts a local file path. Useful for files transferred via network
    share or already sitting on disk.
    """
    file_path = Path(req.path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.path}")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {req.path}")
    if file_path.suffix.lower() not in whisper_service.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{file_path.suffix}'. Supported: {', '.join(whisper_service.SUPPORTED_EXTENSIONS)}",
        )

    timeout = DIARIZE_TIMEOUT if req.diarize else TRANSCRIBE_TIMEOUT
    logger.info("Transcribe file: %s (diarize=%s)", file_path, req.diarize)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(whisper_service.transcribe, file_path, diarize=req.diarize),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Transcription timed out after {timeout}s")
    except Exception as exc:
        logger.exception("Transcription failed for %s", file_path)
        raise HTTPException(status_code=500, detail=f"Transcription error: {exc}")
    return result


@router.get("/status")
async def transcribe_status():
    """Check whether the Whisper model is loaded and GPU memory available."""
    gpu = gpu_monitor.get_gpu_stats()

    return {
        "model_loaded": whisper_service.is_loaded(),
        "whisper_model": whisper_service.settings.WHISPER_MODEL,
        "whisper_device": whisper_service.settings.WHISPER_DEVICE,
        "diarization_loaded": diarize_service.is_loaded(),
        "diarization_model": whisper_service.settings.DIARIZE_MODEL,
        "diarization_device": whisper_service.settings.DIARIZE_DEVICE,
        "gpu": {
            "available": gpu.available,
            "memory_free_mb": gpu.memory_total_mb - gpu.memory_used_mb if gpu.available else 0,
            "memory_total_mb": gpu.memory_total_mb,
        },
    }

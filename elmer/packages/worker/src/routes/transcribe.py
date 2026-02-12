"""Whisper transcription endpoints.

Accepts audio file uploads or local file paths and returns structured
transcription results using faster-whisper (CTranslate2 backend).
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..services import gpu_monitor, whisper_service

logger = logging.getLogger("elmer.worker.transcribe")
router = APIRouter()


class FilePathRequest(BaseModel):
    """Request body for transcribing a file already on disk."""
    path: str


@router.post("")
async def transcribe_upload(file: UploadFile = File(...)):
    """Transcribe an uploaded audio file.

    Accepts multipart file upload. Supported formats: wav, mp3, m4a, flac, ogg.

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

    logger.info("Transcribe upload: %s (%d bytes)", filename, len(audio_bytes))
    result = whisper_service.transcribe_bytes(audio_bytes, suffix=suffix)
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

    logger.info("Transcribe file: %s", file_path)
    result = whisper_service.transcribe(file_path)
    return result


@router.get("/status")
async def transcribe_status():
    """Check whether the Whisper model is loaded and GPU memory available."""
    gpu = gpu_monitor.get_gpu_stats()

    return {
        "model_loaded": whisper_service.is_loaded(),
        "whisper_model": whisper_service.settings.WHISPER_MODEL,
        "whisper_device": whisper_service.settings.WHISPER_DEVICE,
        "gpu": {
            "available": gpu.available,
            "memory_free_mb": gpu.memory_total_mb - gpu.memory_used_mb if gpu.available else 0,
            "memory_total_mb": gpu.memory_total_mb,
        },
    }

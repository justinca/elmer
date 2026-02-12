"""Whisper transcription endpoints using faster-whisper with CUDA."""

import logging
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException, Query

logger = logging.getLogger("elmer.worker.transcribe")
router = APIRouter()

# Lazy-load the model to avoid slow startup and GPU memory usage until needed.
_model = None
_model_name = "base"


def _get_model(model_size: str = "base"):
    """Load the faster-whisper model on first use."""
    global _model, _model_name
    if _model is not None and _model_name == model_size:
        return _model

    from faster_whisper import WhisperModel

    logger.info("Loading faster-whisper model '%s' with CUDA...", model_size)
    start = time.time()
    _model = WhisperModel(model_size, device="cuda", compute_type="float16")
    _model_name = model_size
    logger.info("Model loaded in %.1fs", time.time() - start)
    return _model


@router.post("/audio")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Query(default=None, description="Language code (e.g. 'en'). Auto-detect if omitted."),
    model: str = Query(default="base", description="Whisper model size"),
):
    """Transcribe an uploaded audio file using faster-whisper.

    Returns the full transcript, timed segments, detected language, and duration.
    Supports: wav, mp3, m4a, flac, ogg, webm.
    """
    # Save uploaded file to a temp location (faster-whisper needs a file path).
    suffix = Path(file.filename).suffix if file.filename else ".wav"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                tmp.write(chunk)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {exc}")

    try:
        whisper_model = _get_model(model)

        logger.info("Transcribing %s (%s)...", file.filename, suffix)
        start = time.time()

        kwargs = {"beam_size": 5, "vad_filter": True}
        if language:
            kwargs["language"] = language

        segments_iter, info = whisper_model.transcribe(tmp_path, **kwargs)

        # Collect all segments.
        segments = []
        full_text_parts = []
        for seg in segments_iter:
            segments.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
            })
            full_text_parts.append(seg.text.strip())

        elapsed = time.time() - start
        full_text = " ".join(full_text_parts)

        logger.info(
            "Transcription complete: %.1fs audio in %.1fs (%.1fx realtime), %d segments",
            info.duration, elapsed, info.duration / max(elapsed, 0.1), len(segments),
        )

        return {
            "status": "success",
            "filename": file.filename,
            "transcript": full_text,
            "segments": segments,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration_seconds": round(info.duration, 2),
            "processing_seconds": round(elapsed, 2),
            "model": model,
        }

    except Exception as exc:
        logger.exception("Transcription failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

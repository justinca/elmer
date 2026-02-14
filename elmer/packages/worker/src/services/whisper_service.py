"""Whisper transcription service using faster-whisper (CTranslate2).

Lazy-loads the model on first request to keep startup fast.
Supports wav, mp3, m4a, flac, and ogg audio formats.
"""

import logging
import tempfile
import time
from pathlib import Path

from faster_whisper import WhisperModel

from ..config import settings

logger = logging.getLogger("elmer.worker.whisper")

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}

_model: WhisperModel | None = None


def _load_model() -> WhisperModel:
    """Load the faster-whisper model on first use."""
    global _model
    if _model is not None:
        return _model

    logger.info(
        "Loading Whisper model=%s device=%s ...",
        settings.WHISPER_MODEL,
        settings.WHISPER_DEVICE,
    )
    start = time.time()
    _model = WhisperModel(
        settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        compute_type="float16" if settings.WHISPER_DEVICE == "cuda" else "int8",
    )
    elapsed = time.time() - start
    logger.info("Whisper model loaded in %.1fs", elapsed)
    return _model


def is_loaded() -> bool:
    """Check whether the Whisper model is currently loaded."""
    return _model is not None


def transcribe(audio_path: str | Path, diarize: bool = False) -> dict:
    """Transcribe an audio file and return structured results.

    Args:
        audio_path: Path to audio file.
        diarize: If True, run speaker diarization and add speaker labels.

    Returns:
        Dict with keys: text, segments, language, duration.
        When diarize=True, also includes: diarized, speakers.
    """
    model = _load_model()
    audio_path = Path(audio_path)

    logger.info("Transcribing %s", audio_path.name)
    start = time.time()

    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        word_timestamps=True,
    )

    segments = []
    full_text_parts = []
    for segment in segments_iter:
        segments.append({
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": segment.text.strip(),
            "confidence": round(segment.avg_logprob, 4),
        })
        full_text_parts.append(segment.text.strip())

    elapsed = time.time() - start
    logger.info(
        "Transcribed %s in %.1fs (%.1fs audio, lang=%s)",
        audio_path.name,
        elapsed,
        info.duration,
        info.language,
    )

    result = {
        "text": " ".join(full_text_parts),
        "segments": segments,
        "language": info.language,
        "duration": round(info.duration, 3),
    }

    if diarize:
        from . import diarize_service

        speaker_segments = diarize_service.diarize(audio_path)
        result["segments"] = diarize_service.merge_speakers_into_segments(
            segments, speaker_segments,
        )
        result["diarized"] = True
        result["speakers"] = sorted({s["speaker"] for s in result["segments"]})

    return result


def transcribe_bytes(
    audio_bytes: bytes, suffix: str = ".wav", diarize: bool = False,
) -> dict:
    """Write audio bytes to a temp file and transcribe.

    Args:
        audio_bytes: Raw audio file content.
        suffix: File extension hint for the temp file.
        diarize: If True, run speaker diarization.

    Returns:
        Transcription result dict.
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        return transcribe(tmp_path, diarize=diarize)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

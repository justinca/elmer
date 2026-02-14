"""Speaker diarization service using pyannote.audio.

Lazy-loads the pipeline on first request. Runs on CPU to avoid
GPU memory conflicts with Whisper and Ollama.
"""

import logging
import time
from pathlib import Path

import torch
from pyannote.audio import Pipeline

from ..config import settings

logger = logging.getLogger("elmer.worker.diarize")

_pipeline: Pipeline | None = None


def _load_pipeline() -> Pipeline:
    """Load the pyannote speaker diarization pipeline on first use."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    logger.info(
        "Loading pyannote diarization pipeline=%s device=%s ...",
        settings.DIARIZE_MODEL,
        settings.DIARIZE_DEVICE,
    )
    start = time.time()

    _pipeline = Pipeline.from_pretrained(
        settings.DIARIZE_MODEL,
        use_auth_token=settings.HF_TOKEN or None,
    )
    _pipeline = _pipeline.to(torch.device(settings.DIARIZE_DEVICE))

    elapsed = time.time() - start
    logger.info("Diarization pipeline loaded in %.1fs", elapsed)
    return _pipeline


def is_loaded() -> bool:
    """Check whether the diarization pipeline is currently loaded."""
    return _pipeline is not None


def diarize(audio_path: str | Path) -> list[dict]:
    """Run speaker diarization on an audio file.

    Returns:
        List of dicts: [{speaker, start, end}, ...]
        sorted by start time.
    """
    pipeline = _load_pipeline()
    audio_path = Path(audio_path)

    logger.info("Diarizing %s", audio_path.name)
    start = time.time()

    diarization = pipeline(str(audio_path))

    speaker_segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speaker_segments.append({
            "speaker": speaker,
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
        })

    elapsed = time.time() - start
    logger.info(
        "Diarized %s in %.1fs — %d speaker turns, %d unique speakers",
        audio_path.name,
        elapsed,
        len(speaker_segments),
        len({s["speaker"] for s in speaker_segments}),
    )

    return speaker_segments


def merge_speakers_into_segments(
    whisper_segments: list[dict],
    speaker_segments: list[dict],
) -> list[dict]:
    """Merge pyannote speaker labels into whisper transcription segments.

    For each Whisper segment, find the pyannote speaker with the greatest
    temporal overlap and assign that speaker label.
    """
    result = []
    for seg in whisper_segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        best_speaker = "UNKNOWN"
        best_overlap = 0.0

        for spk in speaker_segments:
            overlap_start = max(seg_start, spk["start"])
            overlap_end = min(seg_end, spk["end"])
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = spk["speaker"]

        result.append({**seg, "speaker": best_speaker})

    return result

"""Transcription pipeline — dispatches audio to the worker for processing."""

import httpx

from .models import TranscriptionRequest, TranscriptionResult


async def transcribe(
    request: TranscriptionRequest,
    worker_url: str = "http://localhost:8101",
) -> TranscriptionResult:
    """Send an audio file to the worker for transcription.

    Args:
        request: The transcription request with file path.
        worker_url: Base URL of the Elmer worker.

    Returns:
        Transcription result from the worker.
    """
    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(request.file_path, "rb") as f:
            resp = await client.post(
                f"{worker_url}/transcribe/audio",
                files={"file": (request.file_path, f, "audio/wav")},
            )
            resp.raise_for_status()
            data = resp.json()

    return TranscriptionResult(
        text=data.get("text", ""),
        status=data.get("status", "unknown"),
    )

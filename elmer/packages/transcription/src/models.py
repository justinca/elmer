"""Transcription data models."""

from pydantic import BaseModel


class TranscriptionRequest(BaseModel):
    """Request to transcribe an audio file."""

    file_path: str
    language: str = "en"
    model: str = "base"


class TranscriptionResult(BaseModel):
    """Result of a transcription."""

    text: str
    status: str

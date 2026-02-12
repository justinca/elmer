"""Transcription data models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    """A single timed segment from Whisper output."""

    start: float
    end: float
    text: str


class TranscriptionResult(BaseModel):
    """Full result of a transcription job."""

    id: int | None = None
    audio_file: str
    transcript: str
    segments: list[TranscriptionSegment] = Field(default_factory=list)
    language: str | None = None
    duration_seconds: float | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class TranscriptionListItem(BaseModel):
    """Summary for list views (no full segment data)."""

    id: int
    audio_file: str
    transcript: str
    language: str | None = None
    duration_seconds: float | None = None
    model: str | None = None
    created_at: datetime | None = None

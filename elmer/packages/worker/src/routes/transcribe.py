"""Whisper transcription endpoints."""

from fastapi import APIRouter, UploadFile, File

router = APIRouter()


@router.post("/audio")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe an uploaded audio file using Whisper.

    TODO: Integrate with local Whisper model.
    """
    return {
        "status": "not_implemented",
        "filename": file.filename,
        "message": "Whisper transcription not yet configured",
    }

"""Meshtastic integration endpoints."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.meshtastic import get_service

router = APIRouter(prefix="/meshtastic", tags=["meshtastic"])
logger = logging.getLogger("elmer.meshtastic.routes")


class SendRequest(BaseModel):
    text: str
    channel: int | None = None


@router.get("/status")
async def get_status():
    """Meshtastic service status."""
    svc = get_service()
    return svc.get_status()


@router.post("/send")
async def send_message(req: SendRequest):
    """Send a test message to the mesh network."""
    svc = get_service()
    if not svc._started:
        raise HTTPException(503, "Meshtastic service not started")

    await svc.send_message(req.text, channel=req.channel)
    return {"status": "sent", "text": req.text}

"""Ollama LLM proxy endpoints."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings

router = APIRouter()

OLLAMA_BASE = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}"


class GenerateRequest(BaseModel):
    """Request body for LLM generation."""

    model: str = "llama3"
    prompt: str
    stream: bool = False


class EmbedRequest(BaseModel):
    """Request body for embedding generation."""

    model: str = "nomic-embed-text"
    input: str | list[str]


@router.post("/generate")
async def generate(request: GenerateRequest):
    """Proxy a generation request to Ollama."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/generate",
                json=request.model_dump(),
            )
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Ollama unreachable: {e}")


@router.post("/embed")
async def embed(request: EmbedRequest):
    """Proxy an embedding request to Ollama."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": request.model, "input": request.input},
            )
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Ollama unreachable: {e}")


@router.get("/models")
async def list_models():
    """List available Ollama models."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Ollama unreachable: {e}")

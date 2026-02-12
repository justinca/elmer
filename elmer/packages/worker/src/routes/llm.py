"""Ollama LLM proxy endpoints.

Forwards requests to the local Ollama instance, with proper SSE
passthrough for streaming responses.
"""

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..config import settings

router = APIRouter()

OLLAMA_BASE = settings.ollama_base_url


async def _proxy_streaming(method: str, path: str, body: dict | None = None):
    """Stream an Ollama response back to the caller via SSE."""
    url = f"{OLLAMA_BASE}{path}"
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0))

    try:
        if method == "POST":
            req = client.build_request("POST", url, json=body)
        else:
            req = client.build_request("GET", url)

        resp = await client.send(req, stream=True)

        if resp.status_code != 200:
            error_body = await resp.aread()
            await resp.aclose()
            await client.aclose()
            raise HTTPException(status_code=resp.status_code, detail=error_body.decode())

        async def generate():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(
            generate(),
            media_type=resp.headers.get("content-type", "application/x-ndjson"),
        )
    except httpx.RequestError as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {e}")


async def _proxy_json(method: str, path: str, body: dict | None = None) -> dict:
    """Forward a request to Ollama and return the JSON response."""
    url = f"{OLLAMA_BASE}{path}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)) as client:
        try:
            if method == "POST":
                resp = await client.post(url, json=body)
            else:
                resp = await client.get(url)

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Ollama unreachable: {e}")


@router.post("/chat")
async def chat(request: Request):
    """Proxy a chat request to Ollama /api/chat.

    Streams by default (Ollama's default). Pass "stream": false in the
    body for a single JSON response.
    """
    body = await request.json()
    if body.get("stream", True):
        return await _proxy_streaming("POST", "/api/chat", body)
    return await _proxy_json("POST", "/api/chat", body)


@router.post("/generate")
async def generate(request: Request):
    """Proxy a generate request to Ollama /api/generate."""
    body = await request.json()
    if body.get("stream", True):
        return await _proxy_streaming("POST", "/api/generate", body)
    return await _proxy_json("POST", "/api/generate", body)


@router.post("/embed")
async def embed(request: Request):
    """Proxy an embeddings request to Ollama /api/embeddings."""
    body = await request.json()
    return await _proxy_json("POST", "/api/embeddings", body)


@router.get("/models")
async def list_models():
    """List available Ollama models."""
    return await _proxy_json("GET", "/api/tags")

"""LLM proxy endpoints — forwards requests to Ollama on the worker."""

import logging

import httpx
from fastapi import APIRouter

from ..config import settings
from ..models.system import (
    LLMChatRequest,
    LLMChatResponse,
    LLMEmbedRequest,
    LLMEmbedResponse,
    LLMMessage,
    LLMModel,
    LLMModelsResponse,
)

router = APIRouter(prefix="/llm", tags=["llm"])
logger = logging.getLogger("elmer.llm")


@router.post("/chat", response_model=LLMChatResponse)
async def llm_chat(request: LLMChatRequest) -> LLMChatResponse:
    """Proxy a chat completion request to Ollama via the worker."""
    url = f"{settings.worker_base_url}/llm/chat"
    payload = {
        "model": request.model,
        "messages": [m.model_dump() for m in request.messages],
        "stream": request.stream,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0)) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
    except httpx.RequestError as exc:
        logger.warning("Worker unreachable for /llm/chat: %s", exc)
        # Fall back to direct Ollama if worker is down.
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0)) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload,
                )
                data = resp.json()
        except httpx.RequestError as exc2:
            logger.error("Ollama also unreachable: %s", exc2)
            return LLMChatResponse(
                model=request.model,
                error=f"LLM service unavailable: {exc2}",
            )

    msg = data.get("message")
    return LLMChatResponse(
        model=data.get("model", request.model),
        message=LLMMessage(**msg) if msg else None,
        done=data.get("done", True),
        total_duration=data.get("total_duration"),
        error=data.get("error"),
    )


@router.post("/embed", response_model=LLMEmbedResponse)
async def llm_embed(request: LLMEmbedRequest) -> LLMEmbedResponse:
    """Proxy an embedding request to Ollama."""
    # Ollama /api/embed accepts "input" as string or list.
    payload = {
        "model": request.model,
        "input": request.input,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json=payload,
            )
            data = resp.json()
    except httpx.RequestError as exc:
        logger.error("Ollama unreachable for /api/embed: %s", exc)
        return LLMEmbedResponse(
            model=request.model,
            error=f"Ollama unreachable: {exc}",
        )

    return LLMEmbedResponse(
        model=data.get("model", request.model),
        embeddings=data.get("embeddings", []),
        error=data.get("error"),
    )


@router.get("/models", response_model=LLMModelsResponse)
async def llm_models() -> LLMModelsResponse:
    """List available models from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            data = resp.json()
    except httpx.RequestError as exc:
        logger.error("Ollama unreachable for /api/tags: %s", exc)
        return LLMModelsResponse(error=f"Ollama unreachable: {exc}")

    models = [
        LLMModel(
            name=m.get("name", ""),
            size=m.get("size"),
            modified_at=m.get("modified_at"),
        )
        for m in data.get("models", [])
    ]
    return LLMModelsResponse(models=models)

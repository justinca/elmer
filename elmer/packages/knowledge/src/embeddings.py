"""Embedding generation for document chunks."""

from typing import Any

import httpx


async def generate_embedding(
    text: str,
    model: str = "nomic-embed-text",
    ollama_url: str = "http://localhost:11434",
) -> list[float]:
    """Generate an embedding vector using Ollama.

    Args:
        text: The text to embed.
        model: The embedding model name.
        ollama_url: Base URL for the Ollama API.

    Returns:
        A list of floats representing the embedding vector.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{ollama_url}/api/embeddings",
            json={"model": model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

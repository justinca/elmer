"""Embedding generation via Ollama on the worker GPU machine."""

import asyncio
import logging
import re

import httpx

from .config import settings

logger = logging.getLogger("elmer.knowledge.embeddings")


class EmbeddingService:
    """Generate vector embeddings by calling the Ollama worker proxy."""

    def __init__(
        self,
        worker_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ):
        self.worker_url = worker_url or settings.worker_embed_url
        self.ollama_url = settings.ollama_embed_url
        self.model = model or settings.EMBEDDING_MODEL
        self.timeout = timeout

    async def _call_embed(
        self, url: str, payload: dict,
    ) -> list[list[float]]:
        """Call an embed endpoint and extract the embeddings list.

        Handles both Ollama response formats:
          - New /api/embed: {"embeddings": [[...], ...]}
          - Old /api/embeddings: {"embedding": [...]}
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()

        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Embedding error: {data['error']}")

        # New format: "embeddings" (list of lists).
        embeddings = data.get("embeddings", [])
        if embeddings:
            return embeddings

        # Old format: "embedding" (single list).
        embedding = data.get("embedding", [])
        if embedding:
            return [embedding]

        return []

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string and return the vector.

        Tries the worker first, falls back to direct Ollama.

        Raises:
            RuntimeError: If both worker and Ollama fail.
        """
        payload = {"model": self.model, "input": text}

        # Try worker first.
        try:
            embeddings = await self._call_embed(self.worker_url, payload)
            if embeddings:
                return embeddings[0]
            logger.warning("Worker returned no embeddings, falling back to Ollama direct")
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker embed failed (%s), falling back to Ollama direct", exc)

        # Fall back to direct Ollama.
        try:
            embeddings = await self._call_embed(self.ollama_url, payload)
            if embeddings:
                return embeddings[0]
        except httpx.TimeoutException:
            logger.error("Timeout waiting for Ollama embed at %s", self.ollama_url)
            raise
        except httpx.ConnectError as exc:
            logger.error("Ollama unreachable at %s: %s", self.ollama_url, exc)
            raise

        raise RuntimeError("No embeddings returned from worker or Ollama")

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 5,
        delay: float = 0.1,
    ) -> list[list[float]]:
        """Embed multiple texts with rate limiting to avoid overwhelming the GPU.

        Processes texts in batches, with a short delay between batches.
        Falls back to direct Ollama if the worker fails.

        Args:
            texts: List of text strings to embed.
            batch_size: Number of texts per batch sent to the worker.
            delay: Seconds to wait between batches.

        Returns:
            List of embedding vectors in the same order as input texts.
        """
        results: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            payload = {"model": self.model, "input": batch}

            # Try worker first, then direct Ollama.
            embeddings: list[list[float]] = []
            try:
                embeddings = await self._call_embed(self.worker_url, payload)
            except (httpx.RequestError, RuntimeError) as exc:
                logger.warning(
                    "Worker batch %d–%d failed (%s), trying Ollama direct",
                    i, i + len(batch), exc,
                )

            if len(embeddings) != len(batch):
                # Worker didn't return the right count — try Ollama directly.
                try:
                    embeddings = await self._call_embed(self.ollama_url, payload)
                except (httpx.RequestError, RuntimeError) as exc:
                    logger.error(
                        "Ollama batch %d–%d also failed: %s", i, i + len(batch), exc,
                    )
                    raise

            if len(embeddings) != len(batch):
                raise RuntimeError(
                    f"Expected {len(batch)} embeddings, got {len(embeddings)}"
                )
            results.extend(embeddings)

            # Rate-limit between batches to avoid GPU overload.
            if i + batch_size < len(texts):
                await asyncio.sleep(delay)

        return results

    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[str]:
        """Split text into overlapping chunks that respect sentence boundaries.

        Tries to break at sentence endings (. ! ? followed by whitespace)
        rather than splitting mid-sentence.

        Args:
            text: The text to chunk.
            chunk_size: Maximum characters per chunk (default from config).
            overlap: Number of overlapping characters between chunks
                (default from config).

        Returns:
            A list of text chunks.
        """
        chunk_size = chunk_size or settings.CHUNK_SIZE
        overlap = overlap or settings.CHUNK_OVERLAP

        text = text.strip()
        if not text:
            return []
        if len(text) <= chunk_size:
            return [text]

        # Split into sentences (keep the delimiter attached).
        sentence_pattern = re.compile(r'(?<=[.!?])\s+')
        sentences = sentence_pattern.split(text)

        chunks: list[str] = []
        current_chunk = ""

        for sentence in sentences:
            # If adding this sentence would exceed the limit, finalize chunk.
            if current_chunk and len(current_chunk) + len(sentence) + 1 > chunk_size:
                chunks.append(current_chunk.strip())

                # Build overlap from the end of the current chunk.
                if overlap > 0:
                    overlap_text = current_chunk[-overlap:]
                    # Try to start the overlap at a sentence boundary.
                    boundary = sentence_pattern.search(overlap_text)
                    if boundary:
                        overlap_text = overlap_text[boundary.end():]
                    current_chunk = overlap_text + " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence

        # Add the last chunk.
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

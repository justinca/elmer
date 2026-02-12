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
        self.model = model or settings.EMBEDDING_MODEL
        self.timeout = timeout

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string and return the vector.

        Calls POST {worker}/llm/embed with the configured model.

        Raises:
            httpx.TimeoutException: If the worker/Ollama doesn't respond
                within the timeout period.
            httpx.HTTPStatusError: If the worker returns an error status.
            RuntimeError: If the response is missing embedding data.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    self.worker_url,
                    json={"model": self.model, "input": text},
                )
                resp.raise_for_status()
            except httpx.TimeoutException:
                logger.error(
                    "Timeout after %.0fs waiting for embedding from %s",
                    self.timeout, self.worker_url,
                )
                raise
            except httpx.ConnectError as exc:
                logger.error("Worker unreachable at %s: %s", self.worker_url, exc)
                raise

        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Embedding error: {data['error']}")

        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise RuntimeError("No embeddings returned from worker")
        return embeddings[0]

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 5,
        delay: float = 0.1,
    ) -> list[list[float]]:
        """Embed multiple texts with rate limiting to avoid overwhelming the GPU.

        Processes texts in batches, with a short delay between batches.

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

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    resp = await client.post(
                        self.worker_url,
                        json={"model": self.model, "input": batch},
                    )
                    resp.raise_for_status()
                except httpx.TimeoutException:
                    logger.error(
                        "Timeout on batch %d–%d (of %d texts)",
                        i, i + len(batch), len(texts),
                    )
                    raise
                except httpx.ConnectError as exc:
                    logger.error("Worker unreachable at %s: %s", self.worker_url, exc)
                    raise

            data = resp.json()
            if data.get("error"):
                raise RuntimeError(f"Batch embedding error: {data['error']}")

            embeddings = data.get("embeddings", [])
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

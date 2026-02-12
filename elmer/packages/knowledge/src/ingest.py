"""Document ingestion engine — reads, chunks, embeds, and stores documents."""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg

from .chunking import ChunkInfo, chunk_document, detect_content_type
from .config import settings
from .embeddings import EmbeddingService

logger = logging.getLogger("elmer.knowledge.ingest")

_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", ".tox",
    ".mypy_cache", ".pytest_cache", ".eggs", ".ruff_cache",
})

_DEFAULT_PATTERNS = [
    "*.md", "*.txt", "*.yaml", "*.yml", "*.json",
    "*.toml", "*.conf", "*.ini", "*.log", "*.csv",
]

_BINARY_CHECK_SIZE = 8192
_MAX_FILE_SIZE = 1_048_576  # 1 MB


@dataclass
class IngestResult:
    """Summary of a directory ingestion run."""

    ingested: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SourceInfo:
    """Metadata about an ingestion source."""

    source: str
    doc_count: int
    latest_update: str | None = None


def _is_binary(file_path: Path) -> bool:
    """Check if a file is binary by looking for null bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(_BINARY_CHECK_SIZE)
        return b"\x00" in chunk
    except OSError:
        return True


def _should_skip_dir(name: str) -> bool:
    """Return True if a directory should be skipped during traversal."""
    return name.startswith(".") or name in _SKIP_DIRS


class DocumentIngestor:
    """Ingests documents into elmer.documents with chunking and embeddings."""

    def __init__(self, pool: asyncpg.Pool | None = None):
        self._pool = pool
        self._embed = EmbeddingService()

    async def connect_db(self) -> None:
        """Create a connection pool if one wasn't provided."""
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            min_size=2,
            max_size=5,
        )
        logger.info("DocumentIngestor connected to PostgreSQL")

    async def close_db(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Not connected — call connect_db() first")
        return self._pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_file(
        self,
        file_path: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Read, chunk, embed, and store a single file.

        Args:
            file_path: Path to the file on disk.
            source: Source identifier (e.g. "elmer-docs", "upload").
            metadata: Optional extra metadata to attach to all chunks.

        Returns:
            Number of chunks stored.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        if path.stat().st_size > _MAX_FILE_SIZE:
            logger.warning("File exceeds 1 MB limit, truncating: %s", file_path)

        content_type = detect_content_type(path)

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.error("Cannot read %s: %s", file_path, exc)
            raise

        # Truncate very large files.
        if len(raw) > _MAX_FILE_SIZE:
            raw = raw[:_MAX_FILE_SIZE]

        chunks = chunk_document(raw, content_type, source_path=str(path))
        if not chunks:
            logger.debug("No chunks produced for %s", file_path)
            return 0

        # Embed all chunks in batch.
        texts = [c.text for c in chunks]
        embeddings = await self._embed_resilient(texts)

        stored = 0
        for chunk, embedding in zip(chunks, embeddings):
            if embedding is None:
                continue
            try:
                await self._upsert_chunk(chunk, embedding, source, content_type, metadata)
                stored += 1
            except Exception:
                logger.warning("Failed to store chunk %d of %s", chunk.index, file_path)

        logger.info("Ingested %s: %d/%d chunks stored (source=%s)", file_path, stored, len(chunks), source)
        return stored

    async def ingest_directory(
        self,
        dir_path: str,
        source: str,
        recursive: bool = True,
        patterns: list[str] | None = None,
    ) -> IngestResult:
        """Walk a directory and ingest matching files.

        Args:
            dir_path: Root directory to scan.
            source: Source identifier for all ingested files.
            recursive: Whether to descend into subdirectories.
            patterns: Glob patterns to match (default: common text formats).

        Returns:
            IngestResult with counts and error details.
        """
        root = Path(dir_path)
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        patterns = patterns or _DEFAULT_PATTERNS
        result = IngestResult()
        start = time.monotonic()

        # Collect matching files.
        files: list[Path] = []
        for pattern in patterns:
            if recursive:
                files.extend(root.rglob(pattern))
            else:
                files.extend(root.glob(pattern))

        # Deduplicate and sort for determinism.
        files = sorted(set(files))

        for file_path in files:
            # Skip files in excluded directories.
            if any(_should_skip_dir(p) for p in file_path.relative_to(root).parts[:-1]):
                result.skipped += 1
                continue

            # Skip hidden files.
            if file_path.name.startswith("."):
                result.skipped += 1
                continue

            # Skip binary files.
            if _is_binary(file_path):
                result.skipped += 1
                continue

            try:
                count = await self.ingest_file(str(file_path), source)
                if count > 0:
                    result.ingested += 1
                else:
                    result.skipped += 1
            except Exception as exc:
                result.errors.append(f"{file_path}: {exc}")
                logger.warning("Failed to ingest %s: %s", file_path, exc)

        elapsed = round(time.monotonic() - start, 2)
        logger.info(
            "Directory ingestion %s: %d ingested, %d skipped, %d errors (%.1fs)",
            dir_path, result.ingested, result.skipped, len(result.errors), elapsed,
        )
        return result

    async def ingest_text(
        self,
        text: str,
        title: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Ingest raw text directly (no file on disk).

        Args:
            text: The text content.
            title: A title for the document.
            source: Source identifier.
            metadata: Optional extra metadata.

        Returns:
            Number of chunks stored.
        """
        if not text or not text.strip():
            return 0

        content_type = "text/plain"
        chunks = chunk_document(text, content_type, source_path=title)
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        embeddings = await self._embed_resilient(texts)

        stored = 0
        for chunk, embedding in zip(chunks, embeddings):
            if embedding is None:
                continue
            try:
                await self._upsert_chunk(chunk, embedding, source, content_type, metadata)
                stored += 1
            except Exception:
                logger.warning("Failed to store chunk %d of text '%s'", chunk.index, title)

        logger.info("Ingested text '%s': %d/%d chunks (source=%s)", title, stored, len(chunks), source)
        return stored

    async def delete_source(self, source: str) -> int:
        """Remove all documents belonging to a source.

        Returns:
            Number of rows deleted.
        """
        pool = self._require_pool()
        result = await pool.execute(
            "DELETE FROM elmer.documents WHERE source = $1", source,
        )
        count = int(result.split()[-1])
        logger.info("Deleted %d documents for source '%s'", count, source)
        return count

    async def list_sources(self) -> list[SourceInfo]:
        """List all ingestion sources with document counts."""
        pool = self._require_pool()
        rows = await pool.fetch("""
            SELECT source, COUNT(*) AS doc_count, MAX(updated_at) AS latest_update
            FROM elmer.documents
            WHERE source IS NOT NULL
            GROUP BY source
            ORDER BY source
        """)
        return [
            SourceInfo(
                source=row["source"],
                doc_count=row["doc_count"],
                latest_update=row["latest_update"].isoformat() if row["latest_update"] else None,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _embed_resilient(self, texts: list[str]) -> list[list[float] | None]:
        """Embed a list of texts, returning None for any that fail."""
        results: list[list[float] | None] = [None] * len(texts)
        try:
            embeddings = await self._embed.embed_batch(texts)
            for i, emb in enumerate(embeddings):
                results[i] = emb
        except Exception:
            # Batch failed — try one at a time.
            logger.warning("Batch embedding failed, falling back to individual embeds")
            for i, text in enumerate(texts):
                try:
                    results[i] = await self._embed.embed_text(text)
                except Exception:
                    logger.warning("Embedding failed for chunk %d, skipping", i)
        return results

    async def _upsert_chunk(
        self,
        chunk: ChunkInfo,
        embedding: list[float],
        source: str,
        content_type: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> int:
        """Insert or update a chunk in elmer.documents."""
        pool = self._require_pool()
        vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

        source_path = chunk.source_path or "text"
        source_path = f"{source_path}#chunk-{chunk.index}"

        title = chunk.section or f"{Path(chunk.source_path or 'text').stem} (chunk {chunk.index})"

        meta = {
            "chunk_index": chunk.index,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "section": chunk.section,
            **(chunk.metadata or {}),
            **(extra_metadata or {}),
        }
        meta_json = json.dumps(meta, default=str)

        row = await pool.fetchrow(
            """
            INSERT INTO elmer.documents
                (source, source_path, title, content, content_type, metadata, embedding, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::vector, now())
            ON CONFLICT (source, source_path)
                WHERE source IS NOT NULL AND source_path IS NOT NULL
            DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                content_type = EXCLUDED.content_type,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding,
                updated_at = now()
            RETURNING id
            """,
            source, source_path, title, chunk.text, content_type, meta_json, vec_str,
        )
        return row["id"]

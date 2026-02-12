"""Vector store — pgvector-backed storage and similarity search."""

import json
import logging
from typing import Any

import asyncpg

from .config import settings

logger = logging.getLogger("elmer.knowledge.vector_store")


class VectorStore:
    """Async pgvector store using asyncpg for embedding storage and retrieval."""

    def __init__(self, pool: asyncpg.Pool | None = None):
        self._pool = pool

    async def connect(self) -> None:
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
            max_size=10,
        )
        logger.info("VectorStore connected to PostgreSQL")

    async def close(self) -> None:
        """Close the connection pool (only if we created it)."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("VectorStore not connected — call connect() first")
        return self._pool

    async def store_embedding(
        self,
        table: str,
        content: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store content with its embedding vector.

        Args:
            table: Target table name (e.g. "documents", "notes", "transcriptions").
                   Will be qualified as elmer.{table}.
            content: The text content.
            embedding: The embedding vector as a list of floats.
            metadata: Optional JSON metadata dict.

        Returns:
            The ID of the inserted row.
        """
        pool = self._require_pool()
        meta_json = json.dumps(metadata or {})
        vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

        query = f"""
            INSERT INTO elmer.{table} (content, embedding, metadata)
            VALUES ($1, $2::vector, $3::jsonb)
            RETURNING id
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, content, vec_str, meta_json)

        row_id = row["id"]
        logger.debug("Stored embedding in elmer.%s (id=%d)", table, row_id)
        return row_id

    async def search_similar(
        self,
        query_embedding: list[float],
        table: str,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Find rows with embeddings most similar to the query vector.

        Uses cosine similarity: 1 - (embedding <=> query_embedding).

        Args:
            query_embedding: The query vector.
            table: Table to search (e.g. "documents", "notes", "transcriptions").
            limit: Maximum results to return.
            threshold: Minimum cosine similarity score (0.0–1.0).

        Returns:
            List of dicts with id, content, metadata, and score, ordered by
            descending similarity.
        """
        pool = self._require_pool()
        vec_str = "[" + ",".join(str(f) for f in query_embedding) + "]"

        query = f"""
            SELECT id, content, metadata,
                   1 - (embedding <=> $1::vector) AS score
            FROM elmer.{table}
            WHERE embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) >= $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, vec_str, threshold, limit)

        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "score": float(row["score"]),
                "source": table,
            })
        return results

    async def delete_by_source(self, source: str, table: str) -> int:
        """Delete all rows matching a source value.

        Args:
            source: The source identifier to match.
            table: Table to delete from.

        Returns:
            Number of rows deleted.
        """
        pool = self._require_pool()
        query = f"DELETE FROM elmer.{table} WHERE source = $1"
        async with pool.acquire() as conn:
            result = await conn.execute(query, source)
        count = int(result.split()[-1])
        logger.info("Deleted %d rows from elmer.%s where source=%s", count, table, source)
        return count

"""Unified search — query across all knowledge base tables."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from .config import settings
from .embeddings import EmbeddingService

logger = logging.getLogger("elmer.knowledge.search")

# Column mappings per table — each table stores content and paths differently.
_TABLE_CONFIG: dict[str, dict[str, str | None]] = {
    "documents": {
        "content_col": "content",
        "path_col": "source_path",
        "title_col": "title",
        "source_col": "source",
    },
    "notes": {
        "content_col": "content",
        "path_col": "source_path",
        "title_col": "title",
        "source_col": "source",
    },
    "transcriptions": {
        "content_col": "transcript",
        "path_col": "audio_file",
        "title_col": None,
        "source_col": None,
    },
}

# User-friendly aliases → canonical table names.
_SOURCE_ALIASES: dict[str, str] = {
    "docs": "documents",
    "documents": "documents",
    "notes": "notes",
    "transcripts": "transcriptions",
    "transcriptions": "transcriptions",
}


@dataclass
class SearchResult:
    """A single search result with content, source info, and similarity score."""

    content: str
    source: str
    source_path: str | None = None
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    title: str | None = None


class UnifiedSearch:
    """Search across all knowledge base tables using vector similarity."""

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
        logger.info("UnifiedSearch connected to PostgreSQL")

    async def close_db(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Not connected — call connect_db() first")
        return self._pool

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
        threshold: float = 0.5,
    ) -> list[SearchResult]:
        """Search across knowledge base tables.

        Args:
            query: Natural language search query.
            sources: Which tables/sources to search. Accepts friendly names
                     ("docs", "notes", "transcripts") or canonical table names.
                     None means search all tables.
            limit: Maximum total results to return.
            threshold: Minimum cosine similarity score (0.0–1.0).

        Returns:
            List of SearchResult objects sorted by descending similarity.
        """
        # Resolve source names to table names.
        if sources:
            tables = []
            for src in sources:
                table = _SOURCE_ALIASES.get(src.lower())
                if table and table not in tables:
                    tables.append(table)
            if not tables:
                logger.warning("No valid sources in %s, searching all", sources)
                tables = list(_TABLE_CONFIG.keys())
        else:
            tables = list(_TABLE_CONFIG.keys())

        # Embed the query.
        query_embedding = await self._embed.embed_text(query)
        vec_str = "[" + ",".join(str(f) for f in query_embedding) + "]"

        # Search each table concurrently.
        tasks = [
            self._search_table(vec_str, table, limit, threshold)
            for table in tables
        ]
        results_per_table = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results, skipping tables that errored.
        all_results: list[SearchResult] = []
        for table, result in zip(tables, results_per_table):
            if isinstance(result, Exception):
                logger.warning("Search failed for table %s: %s", table, result)
                continue
            all_results.extend(result)

        # Sort by score descending, take top N.
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:limit]

    async def _search_table(
        self,
        vec_str: str,
        table: str,
        limit: int,
        threshold: float,
    ) -> list[SearchResult]:
        """Run similarity search on a single table."""
        pool = self._require_pool()
        config = _TABLE_CONFIG[table]
        content_col = config["content_col"]
        path_col = config["path_col"]
        title_col = config["title_col"]

        # Build SELECT columns.
        select_cols = [
            "id",
            f"{content_col} AS content",
            "metadata",
            f"1 - (embedding <=> $1::vector) AS score",
        ]
        if path_col:
            select_cols.append(f"{path_col} AS source_path")
        if title_col:
            select_cols.append(f"{title_col} AS title")

        query = f"""
            SELECT {', '.join(select_cols)}
            FROM elmer.{table}
            WHERE embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) >= $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """

        rows = await pool.fetch(query, vec_str, threshold, limit)

        results: list[SearchResult] = []
        for row in rows:
            meta_raw = row["metadata"]
            if isinstance(meta_raw, str):
                meta = json.loads(meta_raw)
            elif meta_raw is not None:
                meta = dict(meta_raw) if hasattr(meta_raw, "items") else {}
            else:
                meta = {}

            results.append(SearchResult(
                content=row["content"] or "",
                source=table,
                source_path=row.get("source_path"),
                score=float(row["score"]),
                metadata=meta,
                id=row["id"],
                title=row.get("title"),
            ))

        return results

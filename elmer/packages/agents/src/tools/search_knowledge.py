"""Search knowledge tool — vector similarity search across the knowledge base."""

import logging
from typing import Any

import httpx

from .base import BaseTool, ToolResult

logger = logging.getLogger("elmer.agents.tools.search_knowledge")

_EMBED_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)

# Map user-friendly source names to database table names.
_SOURCE_TABLE_MAP = {
    "docs": "documents",
    "documents": "documents",
    "notes": "notes",
    "transcripts": "transcriptions",
    "transcriptions": "transcriptions",
}

# Content column differs per table.
_CONTENT_COL = {"documents": "content", "notes": "content", "transcriptions": "transcript"}
_PATH_COL = {"documents": "source_path", "notes": "source_path", "transcriptions": "audio_file"}
_TITLE_COL = {"documents": "title", "notes": "title", "transcriptions": None}


class SearchKnowledgeTool(BaseTool):
    name = "search_knowledge"
    description = "Search the knowledge base (documents, notes, transcriptions) for relevant information."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
            },
            "required": ["query"],
        }

    async def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        query = arguments.get("query", "")
        if not query.strip():
            return ToolResult(success=False, error="Empty search query")

        settings = context["settings"]
        db = context["db"]

        # Resolve which tables to search.
        raw_sources = self.config.get("sources", ["docs", "notes", "transcripts"])
        tables = []
        for src in raw_sources:
            table = _SOURCE_TABLE_MAP.get(src)
            if table and table not in tables:
                tables.append(table)

        # Get embedding for the query.
        try:
            embedding = await _get_embedding(query, settings)
        except Exception as exc:
            return ToolResult(success=False, error=f"Embedding failed: {exc}")

        vec_str = "[" + ",".join(str(f) for f in embedding) + "]"

        # Search each table.
        all_results: list[dict[str, Any]] = []
        for table in tables:
            content_col = _CONTENT_COL[table]
            path_col = _PATH_COL[table]
            title_col = _TITLE_COL[table]

            cols = [
                "id",
                f"{content_col} AS content",
                f"1 - (embedding <=> $1::vector) AS score",
            ]
            if path_col:
                cols.append(f"{path_col} AS source_path")
            if title_col:
                cols.append(f"{title_col} AS title")

            query_sql = f"""
                SELECT {', '.join(cols)}
                FROM elmer.{table}
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> $1::vector) >= $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """
            try:
                rows = await db.fetch_all(query_sql, vec_str, 0.3, 5)
                for row in rows:
                    content = row.get("content") or ""
                    all_results.append({
                        "content": content[:2000],
                        "source": table,
                        "source_path": row.get("source_path"),
                        "title": row.get("title"),
                        "score": round(float(row["score"]), 4),
                    })
            except Exception:
                logger.warning("Knowledge search failed for table %s", table)

        # Sort by score and return top results.
        all_results.sort(key=lambda r: r["score"], reverse=True)
        top = all_results[:5]

        return ToolResult(
            success=True,
            data={"results": top, "query": query, "tables_searched": tables},
        )


async def _get_embedding(text: str, settings: Any) -> list[float]:
    """Generate embedding via worker, falling back to Ollama direct."""
    worker_url = f"http://{settings.ELMER_WORKER_HOST}:{settings.ELMER_WORKER_PORT}/llm/embed"
    ollama_url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/embed"
    payload = {"model": "nomic-embed-text", "input": text}

    async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT) as client:
        try:
            resp = await client.post(worker_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings") or []
            if embeddings:
                return embeddings[0]
            embedding = data.get("embedding") or []
            if embedding:
                return embedding
            logger.warning("Worker returned no embeddings, falling back to Ollama direct")
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker embed failed (%s), falling back to Ollama direct", exc)

    async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT) as client:
        resp = await client.post(ollama_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings") or []
        if embeddings:
            return embeddings[0]
        embedding = data.get("embedding") or []
        if embedding:
            return embedding

    raise RuntimeError("No embeddings returned from worker or Ollama")

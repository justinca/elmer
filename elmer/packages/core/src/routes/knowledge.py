"""Knowledge endpoints — embedding generation and semantic search."""

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..services import db

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger("elmer.knowledge")

EMBED_TIMEOUT = 60.0

# Allowed tables for search — prevents SQL injection via table name.
_ALLOWED_TABLES = {"documents", "notes", "transcriptions"}

# Map user-friendly source names to table names.
_SOURCE_TABLE_MAP = {
    "docs": "documents",
    "documents": "documents",
    "notes": "notes",
    "transcripts": "transcriptions",
    "transcriptions": "transcriptions",
}

# The text content column differs per table.
_CONTENT_COLUMN = {
    "documents": "content",
    "notes": "content",
    "transcriptions": "transcript",
}


# --- Request / Response models ---


class EmbedRequest(BaseModel):
    text: str
    model: str = "nomic-embed-text"


class EmbedResponse(BaseModel):
    embedding: list[float]
    model: str
    dimensions: int


class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    sources: list[str] = Field(default_factory=lambda: ["notes", "docs", "transcripts"])
    threshold: float = 0.7


class SearchResult(BaseModel):
    content: str
    source: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    id: int | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str


# --- Helpers ---


async def _get_embedding(text: str, model: str = "nomic-embed-text") -> list[float]:
    """Generate an embedding vector via worker, falling back to Ollama direct."""
    worker_url = f"{settings.worker_base_url}/llm/embed"
    ollama_url = f"{settings.ollama_base_url}/api/embed"
    payload = {"model": model, "input": text}

    # Try worker first (proxies to Ollama on the GPU machine).
    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        try:
            resp = await client.post(worker_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(data["error"])
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
            logger.warning("Worker returned no embeddings, falling back to Ollama direct")
        except (httpx.RequestError, RuntimeError) as exc:
            logger.warning("Worker embed failed (%s), falling back to Ollama direct", exc)

    # Fall back to Ollama directly.
    async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
        try:
            resp = await client.post(ollama_url, json=payload)
            resp.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail=f"Embedding request timed out after {EMBED_TIMEOUT}s — "
                       "Ollama may be overloaded",
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=502,
                detail="Cannot reach worker or Ollama for embeddings — "
                       "are they running?",
            )

    data = resp.json()
    if data.get("error"):
        raise HTTPException(status_code=502, detail=f"Embedding error: {data['error']}")

    embeddings = data.get("embeddings", [])
    if not embeddings:
        raise HTTPException(status_code=502, detail="No embeddings returned")
    return embeddings[0]


async def _search_table(
    vec_str: str,
    table: str,
    limit: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """Run cosine similarity search on a single table."""
    content_col = _CONTENT_COLUMN.get(table, "content")
    query = f"""
        SELECT id, {content_col} AS content, metadata,
               1 - (embedding <=> $1::vector) AS score
        FROM elmer.{table}
        WHERE embedding IS NOT NULL
          AND 1 - (embedding <=> $1::vector) >= $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
    """
    rows = await db.fetch_all(query, vec_str, threshold, limit)
    return [
        {
            "id": row["id"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "score": float(row["score"]),
            "source": table,
        }
        for row in rows
    ]


# --- Endpoints ---


@router.post("/embed", response_model=EmbedResponse)
async def embed_text(request: EmbedRequest) -> EmbedResponse:
    """Embed a text string and return the vector."""
    embedding = await _get_embedding(request.text, request.model)
    return EmbedResponse(
        embedding=embedding,
        model=request.model,
        dimensions=len(embedding),
    )


@router.post("/search", response_model=SearchResponse)
async def semantic_search(request: SearchRequest) -> SearchResponse:
    """Semantic search across knowledge sources.

    Embeds the query, then searches the requested tables using cosine
    similarity.  Results are merged and ranked by score.
    """
    # Resolve source names to table names, validating input.
    tables: list[str] = []
    for src in request.sources:
        table = _SOURCE_TABLE_MAP.get(src.lower())
        if table is None or table not in _ALLOWED_TABLES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown source '{src}'. "
                       f"Valid sources: {sorted(_SOURCE_TABLE_MAP.keys())}",
            )
        if table not in tables:
            tables.append(table)

    # Generate query embedding.
    query_embedding = await _get_embedding(request.query)
    vec_str = "[" + ",".join(str(f) for f in query_embedding) + "]"

    # Search each table and merge results.
    all_results: list[dict[str, Any]] = []
    for table in tables:
        try:
            rows = await _search_table(vec_str, table, request.limit, request.threshold)
            all_results.extend(rows)
        except RuntimeError:
            # Database not connected — skip this table.
            logger.warning("Skipping %s — database not available", table)

    # Sort merged results by score descending and take top N.
    all_results.sort(key=lambda r: r["score"], reverse=True)
    top = all_results[: request.limit]

    return SearchResponse(
        results=[SearchResult(**r) for r in top],
        query=request.query,
    )

"""Knowledge endpoints — embedding generation, semantic search, and ingestion."""

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..config import settings
from ..services import db

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger("elmer.knowledge")

EMBED_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)

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


class IngestTextRequest(BaseModel):
    text: str
    title: str
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestDirectoryRequest(BaseModel):
    path: str
    source: str
    recursive: bool = True
    patterns: list[str] = Field(default_factory=lambda: ["*.md", "*.txt"])


class IngestDirectoryResponse(BaseModel):
    source: str
    path: str
    ingested: int
    skipped: int
    errors: list[str]


class IngestFileResponse(BaseModel):
    source: str
    source_path: str
    chunks_stored: int
    content_type: str


class IngestTextResponse(BaseModel):
    source: str
    title: str
    chunks_stored: int


class SourceListItem(BaseModel):
    source: str
    doc_count: int
    latest_update: str | None = None


class DeleteSourceResponse(BaseModel):
    source: str
    deleted_count: int


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


# --- Inline chunking for ingestion endpoints ---

_CONTENT_TYPE_MAP = {
    ".md": "text/markdown", ".markdown": "text/markdown",
    ".txt": "text/plain", ".csv": "text/csv",
    ".log": "text/x-log", ".yaml": "text/x-config",
    ".yml": "text/x-config", ".json": "text/x-config",
    ".toml": "text/x-config", ".conf": "text/x-config",
    ".ini": "text/x-config",
}

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".tox"}
_BINARY_CHECK_SIZE = 8192


def _detect_content_type(suffix: str) -> str:
    return _CONTENT_TYPE_MAP.get(suffix.lower(), "text/plain")


def _chunk_for_ingest(
    text: str,
    filename: str = "text",
    chunk_size: int = 500,
) -> list[dict[str, Any]]:
    """Lightweight chunking for the core API ingest endpoints.

    Handles markdown (split on headers) and plaintext (split on paragraphs).
    Returns list of dicts with 'text', 'index', 'title' keys.
    """
    text = text.strip()
    if not text:
        return []

    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem

    # Single-chunk shortcut.
    if len(text) <= chunk_size:
        return [{"text": text, "index": 0, "title": stem}]

    chunks: list[dict[str, Any]] = []

    if suffix in (".md", ".markdown"):
        # Split on markdown headers.
        parts = re.split(r"(?m)^(#{1,3}\s+.+)$", text)
        current_heading = stem
        current_body = ""

        for part in parts:
            if re.match(r"^#{1,3}\s+", part):
                # Flush previous section.
                if current_body.strip():
                    chunks.append({
                        "text": f"{current_heading}\n\n{current_body.strip()}"
                        if current_heading != stem else current_body.strip(),
                        "index": len(chunks),
                        "title": current_heading,
                    })
                current_heading = part.strip().lstrip("#").strip()
                current_body = ""
            else:
                current_body += part

        # Flush last section.
        if current_body.strip():
            chunks.append({
                "text": f"{current_heading}\n\n{current_body.strip()}"
                if current_heading != stem else current_body.strip(),
                "index": len(chunks),
                "title": current_heading,
            })
    else:
        # Paragraph-based splitting.
        paragraphs = re.split(r"\n\n+", text)
        current = ""
        for para in paragraphs:
            candidate = f"{current}\n\n{para}".strip() if current else para
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append({
                        "text": current,
                        "index": len(chunks),
                        "title": f"{stem} (chunk {len(chunks)})",
                    })
                current = para
        if current.strip():
            chunks.append({
                "text": current.strip(),
                "index": len(chunks),
                "title": f"{stem} (chunk {len(chunks)})",
            })

    # Handle oversized chunks by further splitting.
    final: list[dict[str, Any]] = []
    for chunk in chunks:
        if len(chunk["text"]) <= chunk_size * 2:
            chunk["index"] = len(final)
            final.append(chunk)
        else:
            # Split by sentences as last resort.
            sentences = re.split(r"(?<=[.!?])\s+", chunk["text"])
            current_text = ""
            for sent in sentences:
                candidate = f"{current_text} {sent}".strip() if current_text else sent
                if len(candidate) <= chunk_size:
                    current_text = candidate
                else:
                    if current_text:
                        final.append({
                            "text": current_text,
                            "index": len(final),
                            "title": chunk["title"],
                        })
                    current_text = sent
            if current_text.strip():
                final.append({
                    "text": current_text.strip(),
                    "index": len(final),
                    "title": chunk["title"],
                })

    return final


def _is_binary(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            return b"\x00" in f.read(_BINARY_CHECK_SIZE)
    except OSError:
        return True


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


# --- Ingestion endpoints ---


@router.post("/ingest/file", response_model=IngestFileResponse)
async def ingest_file(
    file: UploadFile = File(...),
    source: str = Form("upload"),
):
    """Upload and ingest a document file into the knowledge base."""
    filename = file.filename or "upload.txt"
    suffix = Path(filename).suffix
    content_type = _detect_content_type(suffix)

    # Save to temp file.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)

    try:
        content = tmp_path.read_text(encoding="utf-8", errors="replace")
        # Truncate large files.
        if len(content) > 1_048_576:
            content = content[:1_048_576]

        chunks = _chunk_for_ingest(content, filename)
        if not chunks:
            raise HTTPException(status_code=400, detail="File produced no content to ingest")

        stored = 0
        for chunk_info in chunks:
            try:
                embedding = await _get_embedding(chunk_info["text"])
                vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
                source_path = f"{filename}#chunk-{chunk_info['index']}"
                meta = json.dumps({"chunk_index": chunk_info["index"]})

                await db.execute(
                    """INSERT INTO elmer.documents
                        (source, source_path, title, content, content_type,
                         metadata, embedding, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::vector, now())
                    ON CONFLICT (source, source_path)
                        WHERE source IS NOT NULL AND source_path IS NOT NULL
                    DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
                        content_type=EXCLUDED.content_type, metadata=EXCLUDED.metadata,
                        embedding=EXCLUDED.embedding, updated_at=now()""",
                    source, source_path, chunk_info["title"], chunk_info["text"],
                    content_type, meta, vec_str,
                )
                stored += 1
            except HTTPException:
                raise
            except Exception:
                logger.warning(
                    "Failed to embed/store chunk %d of %s, skipping",
                    chunk_info["index"], filename,
                )

        return IngestFileResponse(
            source=source,
            source_path=filename,
            chunks_stored=stored,
            content_type=content_type,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/ingest/text", response_model=IngestTextResponse)
async def ingest_text_endpoint(request: IngestTextRequest):
    """Ingest raw text into the knowledge base."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")

    chunks = _chunk_for_ingest(request.text, request.title)
    if not chunks:
        raise HTTPException(status_code=400, detail="Text produced no chunks")

    stored = 0
    for chunk_info in chunks:
        try:
            embedding = await _get_embedding(chunk_info["text"])
            vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
            source_path = f"{request.title}#chunk-{chunk_info['index']}"
            meta = json.dumps({
                "chunk_index": chunk_info["index"],
                **(request.metadata or {}),
            }, default=str)

            await db.execute(
                """INSERT INTO elmer.documents
                    (source, source_path, title, content, content_type,
                     metadata, embedding, updated_at)
                VALUES ($1, $2, $3, $4, 'text/plain', $5::jsonb, $6::vector, now())
                ON CONFLICT (source, source_path)
                    WHERE source IS NOT NULL AND source_path IS NOT NULL
                DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
                    content_type=EXCLUDED.content_type, metadata=EXCLUDED.metadata,
                    embedding=EXCLUDED.embedding, updated_at=now()""",
                request.source, source_path, chunk_info["title"],
                chunk_info["text"], meta, vec_str,
            )
            stored += 1
        except HTTPException:
            raise
        except Exception:
            logger.warning(
                "Failed to embed/store chunk %d of '%s', skipping",
                chunk_info["index"], request.title,
            )

    return IngestTextResponse(
        source=request.source,
        title=request.title,
        chunks_stored=stored,
    )


@router.post("/ingest/directory", response_model=IngestDirectoryResponse)
async def ingest_directory(request: IngestDirectoryRequest):
    """Ingest all matching files from a server-side directory."""
    dir_path = Path(request.path)
    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {request.path}")

    # Security: restrict to paths under ~/elmer/ or /app/ (Docker mounts).
    allowed_bases = [Path.home() / "elmer", Path("/app")]
    if not any(dir_path.resolve().is_relative_to(base) for base in allowed_bases):
        raise HTTPException(status_code=403, detail="Directory outside allowed paths")

    ingested = 0
    skipped = 0
    errors: list[str] = []

    # Collect matching files.
    files: list[Path] = []
    for pattern in request.patterns:
        if request.recursive:
            files.extend(dir_path.rglob(pattern))
        else:
            files.extend(dir_path.glob(pattern))
    files = sorted(set(files))

    for file_path in files:
        # Skip excluded dirs and hidden/binary files.
        try:
            rel_parts = file_path.relative_to(dir_path).parts[:-1]
        except ValueError:
            skipped += 1
            continue

        if any(p.startswith(".") or p in _SKIP_DIRS for p in rel_parts):
            skipped += 1
            continue
        if file_path.name.startswith("."):
            skipped += 1
            continue
        if _is_binary(file_path):
            skipped += 1
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            if len(content) > 1_048_576:
                content = content[:1_048_576]

            suffix = file_path.suffix
            content_type = _detect_content_type(suffix)
            chunks = _chunk_for_ingest(content, file_path.name)

            file_stored = 0
            for chunk_info in chunks:
                try:
                    embedding = await _get_embedding(chunk_info["text"])
                    vec_str = "[" + ",".join(str(f) for f in embedding) + "]"
                    source_path = f"{file_path}#chunk-{chunk_info['index']}"
                    meta = json.dumps({"chunk_index": chunk_info["index"]})

                    await db.execute(
                        """INSERT INTO elmer.documents
                            (source, source_path, title, content, content_type,
                             metadata, embedding, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::vector, now())
                        ON CONFLICT (source, source_path)
                            WHERE source IS NOT NULL AND source_path IS NOT NULL
                        DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
                            content_type=EXCLUDED.content_type, metadata=EXCLUDED.metadata,
                            embedding=EXCLUDED.embedding, updated_at=now()""",
                        request.source, source_path, chunk_info["title"],
                        chunk_info["text"], content_type, meta, vec_str,
                    )
                    file_stored += 1
                except HTTPException:
                    raise
                except Exception:
                    logger.warning(
                        "Failed to embed/store chunk %d of %s",
                        chunk_info["index"], file_path.name,
                    )

            if file_stored > 0:
                ingested += 1
            else:
                skipped += 1
        except HTTPException:
            raise
        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")
            logger.warning("Failed to ingest %s: %s", file_path, exc)

    return IngestDirectoryResponse(
        source=request.source,
        path=request.path,
        ingested=ingested,
        skipped=skipped,
        errors=errors,
    )


@router.get("/sources", response_model=list[SourceListItem])
async def list_sources():
    """List all document sources with counts."""
    rows = await db.fetch_all("""
        SELECT source, COUNT(*) AS doc_count, MAX(updated_at) AS latest_update
        FROM elmer.documents
        WHERE source IS NOT NULL
        GROUP BY source
        ORDER BY source
    """)
    return [
        SourceListItem(
            source=r["source"],
            doc_count=r["doc_count"],
            latest_update=str(r["latest_update"]) if r["latest_update"] else None,
        )
        for r in rows
    ]


@router.delete("/source/{source}", response_model=DeleteSourceResponse)
async def delete_source(source: str):
    """Delete all documents belonging to a source."""
    result = await db.execute(
        "DELETE FROM elmer.documents WHERE source = $1", source,
    )
    count = int(result.split()[-1])
    return DeleteSourceResponse(source=source, deleted_count=count)

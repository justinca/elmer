"""Auto-documentation API endpoints."""

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from ..db import connection as db
from ..models.docs import (
    DocGenerationResponse,
    InventoryResponse,
    ManualNoteRequest,
    ManualNoteResponse,
    ServiceCatalogResponse,
)

router = APIRouter(tags=["docs"])

# SystemDocumentor instance — set from main.py lifespan.
_documentor: Any = None


def set_documentor(doc: Any) -> None:
    global _documentor
    _documentor = doc


def _require_documentor():
    if _documentor is None:
        raise HTTPException(status_code=503, detail="Documentation service not available")
    return _documentor


@router.get("/docs/inventory", response_model=InventoryResponse)
async def docs_inventory() -> InventoryResponse:
    """Return the current device inventory."""
    doc = _require_documentor()
    nodes = doc.discover_nodes()
    return InventoryResponse(
        generated_at=datetime.now(timezone.utc),
        devices=nodes,
    )


@router.get("/docs/services", response_model=ServiceCatalogResponse)
async def docs_services() -> ServiceCatalogResponse:
    """Return the current service catalog with live health checks."""
    doc = _require_documentor()
    services = await doc.discover_services()
    return ServiceCatalogResponse(
        generated_at=datetime.now(timezone.utc),
        services=services,
    )


@router.get("/docs/generate", response_model=DocGenerationResponse)
async def docs_generate() -> DocGenerationResponse:
    """Trigger a full documentation regeneration."""
    doc = _require_documentor()
    result = await doc.generate_all()
    return DocGenerationResponse(**result)


@router.post("/docs/note", response_model=ManualNoteResponse)
async def docs_add_note(note: ManualNoteRequest) -> ManualNoteResponse:
    """Store a manual note in elmer.documents."""
    pool = db.get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    now = datetime.now(timezone.utc)
    metadata = {"tags": note.tags} if note.tags else {}

    try:
        row = await db.fetch_one(
            """
            INSERT INTO elmer.documents (source, source_path, title, content, content_type, metadata, updated_at)
            VALUES ('manual', $1, $2, $3, 'text/markdown', $4, now())
            RETURNING id, created_at
            """,
            f"notes/{note.title.lower().replace(' ', '-')}",
            note.title,
            note.content,
            json.dumps(metadata),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to store note: {exc}")

    return ManualNoteResponse(
        id=row["id"],
        title=note.title,
        source="manual",
        created_at=row["created_at"],
    )

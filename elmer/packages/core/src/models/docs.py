"""Auto-documentation request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Inventory ---


class DeviceInfo(BaseModel):
    """A node with hardware metrics from heartbeat metadata."""

    node_id: str
    name: str
    node_type: str = "unknown"
    status: str = "unknown"
    host: str = ""
    port: int = 0
    platform: str = ""
    hostname: str = ""
    cpu_percent: float | None = None
    ram_total_gb: float | None = None
    ram_used_gb: float | None = None
    disk_total_gb: float | None = None
    disk_used_gb: float | None = None
    last_seen: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InventoryResponse(BaseModel):
    """Device inventory snapshot."""

    generated_at: datetime
    devices: list[DeviceInfo]


# --- Service Catalog ---


class ServiceInfo(BaseModel):
    """A known service in the Elmer network."""

    name: str
    device: str = ""
    host: str = ""
    port: int = 0
    status: str = "unknown"
    container: str = ""
    health_endpoint: str = ""


class ServiceCatalogResponse(BaseModel):
    """Service catalog snapshot."""

    generated_at: datetime
    services: list[ServiceInfo]


# --- Doc Generation ---


class DocGenerationResponse(BaseModel):
    """Result of a full documentation generation run."""

    generated_at: datetime
    files_written: list[str]
    changes_detected: bool
    duration_seconds: float


# --- Manual Notes ---


class ManualNoteRequest(BaseModel):
    """Request body for adding a manual note."""

    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class ManualNoteResponse(BaseModel):
    """Response after storing a manual note."""

    id: int
    title: str
    source: str = "manual"
    created_at: datetime

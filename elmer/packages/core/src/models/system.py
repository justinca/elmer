"""System status and request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Health ---


class HealthResponse(BaseModel):
    """Core health check response."""

    status: str
    service: str = "elmer-core"
    version: str = "0.1.0"
    uptime_seconds: float = 0.0


class NodeHealth(BaseModel):
    """Health status of a single node."""

    node_id: str
    name: str
    status: str  # "online", "offline", "unknown"
    host: str
    port: int
    last_seen: datetime | None = None
    node_type: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodesHealthResponse(BaseModel):
    """Aggregated node health."""

    nodes: list[NodeHealth]


class NodeDetailResponse(BaseModel):
    """Detailed status for a single node."""

    name: str
    node_type: str
    status: str
    last_seen: datetime | None = None
    expected_interval: float = 30.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeEvent(BaseModel):
    """A single event from node history."""

    id: int
    timestamp: datetime
    source: str
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)


class NodeHistoryResponse(BaseModel):
    """Recent event history for a node."""

    node: str
    events: list[NodeEvent]


# --- Nodes ---


class NodeStatus(BaseModel):
    """A registered node in the Elmer network."""

    node_id: str
    name: str
    node_type: str  # "worker", "shackpi", "weatherpi"
    host: str
    port: int
    status: str = "unknown"
    last_seen: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodePingResponse(BaseModel):
    """Result of actively pinging a node."""

    node_id: str
    reachable: bool
    latency_ms: float | None = None
    detail: str = ""


# --- LLM ---


class LLMMessage(BaseModel):
    """A single message in an LLM conversation."""

    role: str  # "system", "user", "assistant"
    content: str


class LLMChatRequest(BaseModel):
    """Request body for LLM chat completion."""

    model: str = "llama3"
    messages: list[LLMMessage]
    stream: bool = False


class LLMChatResponse(BaseModel):
    """Response from LLM chat completion."""

    model: str
    message: LLMMessage | None = None
    done: bool = True
    total_duration: int | None = None
    error: str | None = None


class LLMEmbedRequest(BaseModel):
    """Request body for embedding generation."""

    model: str = "nomic-embed-text"
    input: str | list[str]


class LLMEmbedResponse(BaseModel):
    """Response from embedding generation."""

    model: str
    embeddings: list[list[float]] = Field(default_factory=list)
    error: str | None = None


class LLMModel(BaseModel):
    """An available LLM model."""

    name: str
    size: int | None = None
    modified_at: str | None = None


class LLMModelsResponse(BaseModel):
    """List of available models."""

    models: list[LLMModel] = Field(default_factory=list)
    error: str | None = None

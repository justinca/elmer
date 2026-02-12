"""Agent definition models — Pydantic schemas for the Elmer agent framework."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent building blocks
# ---------------------------------------------------------------------------


class AgentTool(BaseModel):
    """A capability an agent can invoke during execution."""

    name: str = Field(
        ...,
        description="Tool identifier: search_knowledge, query_database, "
        "send_telegram, publish_mqtt, call_api, run_script",
    )
    description: str = ""
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific settings (URL, topic, script path, etc.)",
    )


class AgentTrigger(BaseModel):
    """What activates an agent."""

    type: str = Field(
        ...,
        description="Trigger type: mqtt, schedule, api, event",
    )
    # MQTT triggers
    topic: str | None = Field(
        None, description="MQTT topic pattern (for type=mqtt)"
    )
    payload_filter: dict[str, Any] | None = Field(
        None, description="Optional payload field matching (for type=mqtt)"
    )
    # Schedule triggers
    cron: str | None = Field(
        None, description="Cron expression (for type=schedule), e.g. '0 8 * * *'"
    )
    interval_seconds: int | None = Field(
        None, description="Interval in seconds (for type=schedule)"
    )
    # Event triggers
    event_type: str | None = Field(
        None,
        description="Internal event type (for type=event): "
        "node_offline, transcription_complete, sync_complete, etc.",
    )
    # General
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional trigger-specific settings",
    )


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------


class AgentDefinition(BaseModel):
    """Full definition of an Elmer agent — what it is, what it can do,
    and when it should act."""

    id: int | None = None
    name: str = Field(
        ...,
        description="Unique slug: dx-spotter, daily-summary, system-monitor",
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        min_length=2,
        max_length=64,
    )
    display_name: str = Field(
        "", description="Human-friendly name: 'DX Spotter', 'Daily Summary Agent'"
    )
    description: str = ""
    system_prompt: str = Field(
        "", description="The agent's personality, instructions, and context"
    )
    model: str = Field(
        "llama3.1:8b", description="Ollama model to use for inference"
    )
    tools: list[AgentTool] = Field(default_factory=list)
    triggers: list[AgentTrigger] = Field(default_factory=list)
    output_channels: list[str] = Field(
        default_factory=list,
        description="Where results go: telegram, mqtt, dashboard, log",
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Agent-specific configuration"
    )
    enabled: bool = True
    max_concurrent: int = Field(1, ge=1, le=10)
    timeout_seconds: int = Field(120, ge=5, le=3600)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Agent runs — execution history
# ---------------------------------------------------------------------------


class AgentRun(BaseModel):
    """Record of a single agent execution."""

    id: int | None = None
    agent_id: int
    agent_name: str = ""
    trigger_type: str = Field(
        ..., description="What triggered this run: mqtt, schedule, api, event"
    )
    trigger_data: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(
        "pending",
        description="pending, running, completed, failed, timeout",
    )
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# API request/response helpers
# ---------------------------------------------------------------------------


class AgentCreateRequest(BaseModel):
    """Request body for creating an agent via API."""

    name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
    display_name: str = ""
    description: str = ""
    system_prompt: str = ""
    model: str = "llama3.1:8b"
    tools: list[AgentTool] = Field(default_factory=list)
    triggers: list[AgentTrigger] = Field(default_factory=list)
    output_channels: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    max_concurrent: int = 1
    timeout_seconds: int = 120


class AgentUpdateRequest(BaseModel):
    """Request body for updating an agent (all fields optional)."""

    display_name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    tools: list[AgentTool] | None = None
    triggers: list[AgentTrigger] | None = None
    output_channels: list[str] | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    max_concurrent: int | None = None
    timeout_seconds: int | None = None


class AgentRunRequest(BaseModel):
    """Request body for manually triggering an agent."""

    input: dict[str, Any] = Field(default_factory=dict)


class AgentRunSummary(BaseModel):
    """Lightweight run info for list views."""

    id: int
    agent_name: str
    trigger_type: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None

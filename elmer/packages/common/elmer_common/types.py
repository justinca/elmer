"""Shared type definitions used across Elmer packages."""

from enum import StrEnum

from pydantic import BaseModel


class ServiceName(StrEnum):
    """Known Elmer services."""

    CORE = "elmer-core"
    WORKER = "elmer-worker"
    DASHBOARD = "elmer-dashboard"
    TELEGRAM = "elmer-telegram"
    AGENTS = "elmer-agents"
    KNOWLEDGE = "elmer-knowledge"


class DeviceRole(StrEnum):
    """Device roles in the Elmer network."""

    HUB = "hub"
    WORKER = "worker"
    SENSOR = "sensor"
    RADIO = "radio"


class ServiceStatus(BaseModel):
    """Status of a single service."""

    name: ServiceName
    status: str
    host: str
    port: int


class MQTTMessage(BaseModel):
    """Standard MQTT message envelope."""

    topic: str
    payload: str
    source: ServiceName

"""Tests for the health check endpoint.

Uses a test-scoped lifespan override so that MQTT and Postgres
connections are not required during testing.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import app
from src.routes import health


@asynccontextmanager
async def _test_lifespan(app: FastAPI):
    """Minimal lifespan that skips external services."""
    import time

    health.set_start_time(time.time())
    yield


# Override the app lifespan for tests.
app.router.lifespan_context = _test_lifespan

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "elmer-core"
    assert data["version"] == "0.1.0"
    assert "uptime_seconds" in data


def test_health_nodes_returns_list():
    response = client.get("/health/nodes")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert isinstance(data["nodes"], list)


def test_nodes_list():
    response = client.get("/nodes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_llm_models_returns_gracefully():
    """LLM models endpoint should return an error message, not crash."""
    response = client.get("/llm/models")
    assert response.status_code == 200
    data = response.json()
    # Ollama isn't running in test, so we get an error field.
    assert "models" in data or "error" in data

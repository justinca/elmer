"""Elmer Core — FastAPI application entry point."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import docs, health, knowledge, llm, nodes, notes, transcription
from .services import autodoc, db, mqtt_service
from .services.autodoc import SystemDocumentor, _periodic_generation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("elmer.core")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of background services."""
    logger.info("Elmer Core starting up...")

    # Record startup time for uptime tracking.
    health.set_start_time(time.time())

    # Connect to PostgreSQL (non-fatal if unavailable).
    await db.connect()

    # Start MQTT client, heartbeat, and stale-node checker in background.
    mqtt_stop = asyncio.Event()
    mqtt_task = asyncio.create_task(mqtt_service.run(mqtt_stop))

    # Give MQTT a moment to connect before accepting requests.
    await asyncio.sleep(0.5)

    # Wire NodeMonitor into health routes for the new /health/nodes endpoints.
    node_monitor = mqtt_service.get_node_monitor()
    if node_monitor is not None:
        health.set_node_monitor(node_monitor)

    # Wire up the auto-documentation system.
    documentor = SystemDocumentor(node_monitor)
    autodoc.set_documentor(documentor)
    docs.set_documentor(documentor)

    # Fire initial doc generation as a background task.
    asyncio.create_task(documentor.generate_all())

    # Start periodic doc regeneration.
    autodoc_stop = asyncio.Event()
    autodoc_task = asyncio.create_task(
        _periodic_generation(documentor, autodoc_stop, settings.AUTODOC_INTERVAL_HOURS)
    )

    logger.info("Elmer Core ready — http://%s:%s", settings.ELMER_CORE_HOST, settings.ELMER_CORE_PORT)

    yield

    # Shutdown
    logger.info("Elmer Core shutting down...")

    # Stop autodoc periodic task.
    autodoc_stop.set()
    try:
        await asyncio.wait_for(autodoc_task, timeout=5.0)
    except asyncio.TimeoutError:
        autodoc_task.cancel()

    # Signal MQTT loop to stop (run() handles offline publish + cleanup).
    mqtt_stop.set()

    try:
        await asyncio.wait_for(mqtt_task, timeout=10.0)
    except asyncio.TimeoutError:
        mqtt_task.cancel()

    await db.close()
    logger.info("Elmer Core stopped.")


app = FastAPI(
    title="Elmer Core API",
    description="Central API gateway for the Elmer home lab OS",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(nodes.router)
app.include_router(llm.router)
app.include_router(docs.router)
app.include_router(knowledge.router)
app.include_router(transcription.router)
app.include_router(notes.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "elmer_core.main:app",
        host=settings.ELMER_CORE_HOST,
        port=settings.ELMER_CORE_PORT,
        reload=True,
    )

"""Elmer Core — FastAPI application entry point."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import agents, chat, contest, docs, dx, health, homeassistant, knowledge, llm, log, meshtastic, nodes, notes, pota, propagation, radio, transcription
from .services import autodoc, db, mqtt_service
from .services.autodoc import SystemDocumentor
from .services.scheduler import create_scheduler

from elmer_common.logging import setup_logger as _setup_logger

_setup_logger("elmer", logging.INFO)  # root elmer logger with local-tz timestamps
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

    # Start the unified scheduler (autodoc regen, docs ingestion, etc.).
    scheduler = create_scheduler()
    await scheduler.start()

    # Sync agent definitions from YAML into the database.
    try:
        result = await agents.sync_agent_definitions("/app/agent_definitions")
        logger.info("Agent definitions synced: %s", result)
    except Exception:
        logger.exception("Failed to sync agent definitions (non-fatal)")

    # Start the agent orchestrator (trigger system).
    from .services.orchestrator_service import start_orchestrator, stop_orchestrator

    orchestrator = None
    try:
        orchestrator = await start_orchestrator()
        logger.info("Agent orchestrator started: %s", orchestrator.get_status())
    except Exception:
        logger.exception("Failed to start agent orchestrator (non-fatal)")

    # Start DX cluster client and populate needs list.
    from .services.dx_cluster import get_client as get_dx_client
    from .services.needs_list import get_needs_list

    dx_client = get_dx_client()
    try:
        await dx_client.connect()
    except Exception:
        logger.exception("Failed to start DX cluster client (non-fatal)")

    try:
        nl = get_needs_list()
        await nl.populate_starter()
    except Exception:
        logger.exception("Failed to populate needs list (non-fatal)")

    # Start Meshtastic CalvertCasa responder (after MQTT is connected).
    from .services.meshtastic import get_service as get_mesh_service

    mesh_service = get_mesh_service()
    try:
        await mesh_service.start()
        logger.info("Meshtastic responder started on %s", settings.MESHTASTIC_CHANNEL_TOPIC)
    except Exception:
        logger.exception("Failed to start Meshtastic responder (non-fatal)")

    logger.info("Elmer Core ready — http://%s:%s", settings.ELMER_CORE_HOST, settings.ELMER_CORE_PORT)

    yield

    # Shutdown
    logger.info("Elmer Core shutting down...")

    # Stop DX cluster client.
    try:
        await dx_client.disconnect()
    except Exception:
        pass

    # Stop the orchestrator first (finish running agents).
    if orchestrator is not None:
        await stop_orchestrator()

    # Stop the scheduler.
    await scheduler.stop()

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
app.include_router(chat.router)
app.include_router(agents.router)
app.include_router(propagation.router)
app.include_router(dx.router)
app.include_router(log.router)
app.include_router(pota.router)
app.include_router(contest.router)
app.include_router(radio.router)
app.include_router(homeassistant.router)
app.include_router(meshtastic.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "elmer_core.main:app",
        host=settings.ELMER_CORE_HOST,
        port=settings.ELMER_CORE_PORT,
        reload=True,
    )

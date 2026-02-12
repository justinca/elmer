"""Elmer Core — FastAPI application entry point."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import health, llm, nodes
from .services import db, mqtt_service

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

    logger.info("Elmer Core ready — http://%s:%s", settings.ELMER_CORE_HOST, settings.ELMER_CORE_PORT)

    yield

    # Shutdown
    logger.info("Elmer Core shutting down...")

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.ELMER_CORE_HOST,
        port=settings.ELMER_CORE_PORT,
        reload=True,
    )

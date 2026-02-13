"""Elmer Worker — FastAPI application entry point.

Runs on the Windows desktop with GPU access. Provides LLM inference
(via local Ollama) and audio transcription (via faster-whisper) to the
Elmer network.
"""

import json
import logging
import platform
import threading
import time
from contextlib import asynccontextmanager

import paho.mqtt.client as mqtt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import health, llm, log4om, obsidian, transcribe
from .services import gpu_monitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("elmer.worker")

HEARTBEAT_INTERVAL = 30  # seconds
MQTT_RETRY_INTERVAL = 5  # seconds


def _heartbeat_thread(stop_event: threading.Event, start_time: float):
    """Publish heartbeat to MQTT every HEARTBEAT_INTERVAL seconds.

    Runs in a dedicated daemon thread using the synchronous paho-mqtt
    client, avoiding the Windows asyncio event-loop compatibility issues
    that affect aiomqtt.
    """
    while not stop_event.is_set():
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if settings.MQTT_USER:
            client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD or None)

        try:
            client.connect(settings.MQTT_HOST, settings.MQTT_PORT)
            logger.info(
                "MQTT heartbeat connected to %s:%s",
                settings.MQTT_HOST,
                settings.MQTT_PORT,
            )

            while not stop_event.is_set():
                gpu = gpu_monitor.get_gpu_stats()

                payload = json.dumps({
                    "status": "online",
                    "hostname": platform.node(),
                    "uptime_seconds": round(time.time() - start_time, 1),
                    "gpu_status": {
                        "available": gpu.available,
                        "name": gpu.gpu_name,
                        "temperature_c": gpu.temperature_c,
                        "utilization_pct": gpu.utilization_pct,
                        "memory_used_mb": gpu.memory_used_mb,
                        "memory_total_mb": gpu.memory_total_mb,
                    },
                    "ollama_status": "unknown",
                })

                client.publish("elmer/worker/heartbeat", payload)
                logger.debug("Heartbeat published")
                stop_event.wait(timeout=HEARTBEAT_INTERVAL)

        except Exception as exc:
            logger.warning(
                "MQTT heartbeat error (%s), retrying in %ds...",
                exc,
                MQTT_RETRY_INTERVAL,
            )
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

        if not stop_event.is_set():
            stop_event.wait(timeout=MQTT_RETRY_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of background services."""
    logger.info("Elmer Worker starting up...")

    start_time = time.time()
    health.set_start_time(start_time)

    # Start MQTT heartbeat in a daemon thread (synchronous paho-mqtt).
    stop_event = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_thread,
        args=(stop_event, start_time),
        daemon=True,
        name="mqtt-heartbeat",
    )
    heartbeat.start()

    logger.info("Elmer Worker ready on port %s", settings.WORKER_PORT)

    yield

    # Shutdown
    logger.info("Elmer Worker shutting down...")
    stop_event.set()
    heartbeat.join(timeout=5.0)

    logger.info("Elmer Worker stopped.")


app = FastAPI(
    title="Elmer Worker",
    description="Windows GPU worker for LLM inference and transcription",
    version="0.1.0",
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
app.include_router(llm.router, prefix="/llm", tags=["llm"])
app.include_router(transcribe.router, prefix="/transcribe", tags=["transcribe"])
app.include_router(log4om.router, prefix="/log4om", tags=["log4om"])
app.include_router(obsidian.router, prefix="/obsidian", tags=["obsidian"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.WORKER_PORT,
        reload=True,
    )

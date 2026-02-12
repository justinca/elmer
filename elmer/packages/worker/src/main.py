"""Elmer Worker — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .routes import health, llm, transcribe


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    yield


app = FastAPI(
    title="Elmer Worker",
    description="Windows GPU worker for LLM inference and transcription",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(llm.router, prefix="/llm", tags=["llm"])
app.include_router(transcribe.router, prefix="/transcribe", tags=["transcribe"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.ELMER_WORKER_HOST,
        port=settings.ELMER_WORKER_PORT,
        reload=True,
    )

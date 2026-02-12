"""Transcription service configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


def _find_env_file() -> str | None:
    """Locate .env by checking multiple paths."""
    candidates = [
        Path(".env"),
        Path(__file__).resolve().parent.parent / ".env",
        Path.home() / "elmer" / ".env",
        Path.home() / "elmer" / "packages" / "transcription" / ".env",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


class TranscriptionSettings(BaseSettings):
    """Settings for the transcription pipeline."""

    # Worker (Windows GPU machine with faster-whisper)
    ELMER_WORKER_HOST: str = "localhost"
    ELMER_WORKER_PORT: int = 8101

    # Embedding (via worker → Ollama, with Ollama direct fallback)
    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434
    EMBEDDING_MODEL: str = "nomic-embed-text"

    # File watcher
    TRANSCRIPTION_WATCH_DIR: str = str(Path.home() / "elmer" / "audio" / "inbox")
    TRANSCRIPTION_PROCESSED_DIR: str = str(Path.home() / "elmer" / "audio" / "processed")

    # PostgreSQL
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "elmer"

    # MQTT
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USER: str = ""
    MQTT_PASSWORD: str = ""

    @property
    def worker_transcribe_url(self) -> str:
        return f"http://{self.ELMER_WORKER_HOST}:{self.ELMER_WORKER_PORT}/transcribe/audio"

    @property
    def worker_embed_url(self) -> str:
        return f"http://{self.ELMER_WORKER_HOST}:{self.ELMER_WORKER_PORT}/llm/embed"

    @property
    def ollama_embed_url(self) -> str:
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}/api/embed"

    model_config = {"env_file": _find_env_file(), "extra": "ignore"}


settings = TranscriptionSettings()

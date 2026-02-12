"""Knowledge service configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


def _find_env_file() -> str | None:
    """Locate .env by checking multiple paths."""
    candidates = [
        Path(".env"),                                    # cwd
        Path(__file__).resolve().parent.parent / ".env", # packages/knowledge/.env
        Path.home() / "elmer" / ".env",                  # repo root
        Path.home() / "elmer" / "packages" / "knowledge" / ".env",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


class KnowledgeSettings(BaseSettings):
    """Settings for the knowledge / embedding service."""

    # Worker (Windows GPU machine running Ollama)
    ELMER_WORKER_HOST: str = "localhost"
    ELMER_WORKER_PORT: int = 8101

    # Ollama direct fallback
    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434

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

    # Embedding
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSIONS: int = 768
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # Obsidian sync
    OBSIDIAN_SYNC_INTERVAL: int = 3600  # seconds

    # Elmer docs auto-ingestion
    ELMER_DOCS_PATH: str = str(Path.home() / "elmer" / "docs")
    DOCS_SYNC_INTERVAL: int = 3600  # seconds

    @property
    def worker_base_url(self) -> str:
        return f"http://{self.ELMER_WORKER_HOST}:{self.ELMER_WORKER_PORT}"

    @property
    def worker_embed_url(self) -> str:
        return f"{self.worker_base_url}/llm/embed"

    @property
    def ollama_embed_url(self) -> str:
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}/api/embed"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = {"env_file": _find_env_file(), "extra": "ignore"}


settings = KnowledgeSettings()

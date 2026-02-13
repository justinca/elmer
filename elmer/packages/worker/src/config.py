"""Elmer Worker — Configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Worker settings loaded from environment variables."""

    # Worker
    WORKER_PORT: int = 8101

    # Ollama (local LLM) — prefixed to avoid collision with Ollama's own OLLAMA_HOST
    ELMER_OLLAMA_HOST: str = "localhost"
    ELMER_OLLAMA_PORT: int = 11434

    # MQTT (broker on the NUC)
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USER: str = ""
    MQTT_PASSWORD: str = ""

    # Whisper transcription
    WHISPER_MODEL: str = "medium.en"
    WHISPER_DEVICE: str = "cuda"

    # Obsidian vault path on this Windows machine
    OBSIDIAN_VAULT_PATH: str = ""

    # Log4OM SQLite database path (read-only access)
    ELMER_LOG4OM_DB_PATH: str = ""

    @property
    def ollama_base_url(self) -> str:
        return f"http://{self.ELMER_OLLAMA_HOST}:{self.ELMER_OLLAMA_PORT}"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

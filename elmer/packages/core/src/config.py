"""Elmer Core — Configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Core
    ELMER_CORE_HOST: str = "0.0.0.0"
    ELMER_CORE_PORT: int = 8100

    # Worker (Windows GPU machine)
    ELMER_WORKER_HOST: str = "localhost"
    ELMER_WORKER_PORT: int = 8101

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

    # Ollama (LLM)
    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""

    # Knowledge base
    OBSIDIAN_VAULT_PATH: str = ""

    @property
    def worker_base_url(self) -> str:
        return f"http://{self.ELMER_WORKER_HOST}:{self.ELMER_WORKER_PORT}"

    @property
    def ollama_base_url(self) -> str:
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

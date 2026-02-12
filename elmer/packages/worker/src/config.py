"""Elmer Worker — Configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Worker settings loaded from environment variables."""

    ELMER_WORKER_HOST: str = "0.0.0.0"
    ELMER_WORKER_PORT: int = 8101

    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

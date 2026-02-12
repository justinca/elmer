"""Elmer Worker — Configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Worker settings loaded from environment variables."""

    ELMER_WORKER_HOST: str = "0.0.0.0"
    ELMER_WORKER_PORT: int = 8101

    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USER: str = ""
    MQTT_PASSWORD: str = ""

    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

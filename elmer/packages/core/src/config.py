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
    TELEGRAM_CHAT_ID: str = ""  # Admin chat ID for agent notifications

    # Agent executor
    AGENT_MAX_CONCURRENT: int = 5  # Global max concurrent agent runs
    AGENT_SCRIPTS_DIR: str = "/app/agent-scripts"

    # Knowledge base
    OBSIDIAN_VAULT_PATH: str = ""

    # DX Cluster
    DX_CLUSTER_HOST: str = "dxc.ve7cc.net"
    DX_CLUSTER_PORT: int = 23
    DX_CLUSTER_CALLSIGN: str = "W0ABE"
    DX_SPOT_RETENTION_HOURS: int = 24

    # POTA
    POTA_HOME_GRID: str = "DN70"
    POTA_HOME_STATE: str = "US-CO"

    # Auto-documentation
    AUTODOC_INTERVAL_HOURS: float = 6.0

    # Home Assistant
    HA_URL: str = ""
    HA_TOKEN: str = ""
    HA_SYNC_INTERVAL: int = 300  # 5 minutes

    # Timezone (used by scheduler, logging, display)
    TIMEZONE: str = "America/Denver"

    # AllStar
    ALLSTAR_NODE: int = 68498
    ALLSTAR_SHACKPI_HOST: str = "shackpi"

    # Meshtastic
    MESHTASTIC_CHANNEL_TOPIC: str = "msh/US/2/json/CalvertCasa/#"
    MESHTASTIC_SEND_TOPIC: str = "msh/US/2/json/mqtt/"
    MESHTASTIC_NODE_ID: int = 2654877601
    MESHTASTIC_IGNORE_FROM: str = "24040934"
    MESHTASTIC_CHANNEL: int = 0

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

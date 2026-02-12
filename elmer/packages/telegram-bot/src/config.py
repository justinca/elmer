"""Elmer Telegram Bot — Configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Bot settings loaded from environment / .env file."""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USERS: str = ""  # comma-separated user IDs

    # Elmer Core API
    ELMER_CORE_HOST: str = "localhost"
    ELMER_CORE_PORT: int = 8100

    # MQTT
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USER: str = ""
    MQTT_PASSWORD: str = ""

    # Quiet hours (24h format, local time)
    QUIET_HOURS_START: int = 22  # 10 PM
    QUIET_HOURS_END: int = 7  # 7 AM

    @property
    def core_base_url(self) -> str:
        return f"http://{self.ELMER_CORE_HOST}:{self.ELMER_CORE_PORT}"

    @property
    def allowed_user_ids(self) -> set[int]:
        if not self.TELEGRAM_ALLOWED_USERS.strip():
            return set()
        return {
            int(uid.strip())
            for uid in self.TELEGRAM_ALLOWED_USERS.split(",")
            if uid.strip().isdigit()
        }

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

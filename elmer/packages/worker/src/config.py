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

    # Speaker diarization (pyannote.audio)
    DIARIZE_MODEL: str = "pyannote/speaker-diarization-3.1"
    DIARIZE_DEVICE: str = "cuda"
    HF_TOKEN: str = ""  # Only needed for first model download

    # Elmer Core (NUC) — for posting transcription results
    ELMER_CORE_HOST: str = "192.168.1.127"
    ELMER_CORE_PORT: int = 8100

    # Folder watcher — polls for new audio files to transcribe
    WATCH_FOLDER: str = ""  # Empty = disabled
    WATCH_INTERVAL_SECONDS: int = 900  # 15 minutes

    # Obsidian vault path on this Windows machine
    OBSIDIAN_VAULT_PATH: str = ""

    # Log4OM SQLite database path (read-only access)
    ELMER_LOG4OM_DB_PATH: str = ""

    # CAT Control / Band Scanner
    CAT_HOST: str = "localhost"
    CAT_PORT: int = 7356
    SCANNER_DWELL_SECONDS: int = 900
    SCANNER_DAYTIME_START_UTC: int = 13   # 1pm UTC = 6am MST
    SCANNER_DAYTIME_END_UTC: int = 4      # 4am UTC = 9pm MST
    SCANNER_AUTO_START: bool = False

    @property
    def ollama_base_url(self) -> str:
        return f"http://{self.ELMER_OLLAMA_HOST}:{self.ELMER_OLLAMA_PORT}"

    @property
    def core_base_url(self) -> str:
        return f"http://{self.ELMER_CORE_HOST}:{self.ELMER_CORE_PORT}"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

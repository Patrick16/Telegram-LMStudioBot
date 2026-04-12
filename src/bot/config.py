from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_OWNER_ID: int
    LMS_HOST: str = "localhost"
    LMS_PORT: int = 1234
    SESSIONS_FILE: str = "data/sessions.json"
    HISTORIES_DIR: str = "data/histories"
    MODEL_PRESETS_FILE: str = "data/model-presets.json"
    SESSION_PRESETS_FILE: str = "data/session-presets.json"
    LOG_LEVEL: str = "INFO"

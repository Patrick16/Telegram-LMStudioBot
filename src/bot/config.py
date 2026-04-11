from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_OWNER_ID: int
    LMS_HOST: str = "localhost"
    LMS_PORT: int = 1234
    SESSIONS_FILE: str = "data/sessions.json"
    LOG_LEVEL: str = "INFO"

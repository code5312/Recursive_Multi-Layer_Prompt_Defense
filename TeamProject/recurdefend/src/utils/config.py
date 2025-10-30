# src/utils/config.py
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    APP_ENV: str = Field("dev", env="APP_ENV")
    LCE_BLOCK_THRESHOLD: float = 0.9
    LCE_FLAG_MEAN_THRESHOLD: float = 0.6
    CORE_MODEL_PATH: str = "llama3-local-or-stub"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()

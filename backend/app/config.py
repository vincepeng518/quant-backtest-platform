from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    db_path: str = os.getenv("DB_PATH", "./data/backtest.db")
    log_level: str = os.getenv("LOG_LEVEL", "info")
    cors_origins: list[str] = ["*"]


settings = Settings()
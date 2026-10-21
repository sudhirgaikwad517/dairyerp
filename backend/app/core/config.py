import os
from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    PROJECT_NAME: str = "DairyERP - Smart Dairy Distribution & Processing Enterprise ERP"
    API_V1_STR: str = "/api/v1"
    # Never written in the code: from the environment, else a random key kept in .secret_key
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    
    # Absolute path: the same database is used whatever folder the server is started from
    SQLITE_FALLBACK_URL: str = "sqlite:///" + (PROJECT_ROOT / "dairy_erp.db").as_posix()
    # DATABASE_URL from the environment (SQLite or PostgreSQL); the local SQLite file otherwise
    DATABASE_URL: str = os.getenv("DATABASE_URL") or SQLITE_FALLBACK_URL
    
    # Pricing & Transport Defaults
    DEFAULT_DIESEL_PRICE: float = 95.0
    DEFAULT_DRIVER_DAY_COST: float = 800.0
    DEFAULT_MILK_COST_PRICE: float = 42.0

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

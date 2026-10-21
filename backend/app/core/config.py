import os
from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    PROJECT_NAME: str = "DairyERP - Smart Dairy Distribution & Processing Enterprise ERP"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dairy_erp_super_secret_jwt_key_2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    
    # Database URL: Primary is PostgreSQL, fallback to SQLite for immediate local plug-and-play
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/dairy_erp"
    )
    # Absolute path: the same database is used whatever folder the server is started from
    SQLITE_FALLBACK_URL: str = "sqlite:///" + (PROJECT_ROOT / "dairy_erp.db").as_posix()
    
    # Pricing & Transport Defaults
    DEFAULT_DIESEL_PRICE: float = 95.0
    DEFAULT_DRIVER_DAY_COST: float = 800.0
    DEFAULT_MILK_COST_PRICE: float = 42.0

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

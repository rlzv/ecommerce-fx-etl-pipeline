from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_environment: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql://etl_user:etl_password@localhost:5433/ecommerce_etl"

    orders_api_url: str = "https://jzozteoirwfczccltcdr.supabase.co/rest/v1/orders_raw"
    orders_api_key: SecretStr = SecretStr("")
    orders_page_size: int = Field(default=1000, ge=1, le=1000)
    frankfurter_base_url: str = "https://api.frankfurter.dev/v2"
    fx_lookback_days: int = Field(default=7, ge=1, le=31)

    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use the PostgreSQL scheme")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable-enough settings object per process."""

    return Settings()

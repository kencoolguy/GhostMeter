from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    APP_NAME: str = "GhostMeter"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # PostgreSQL (individual vars shared with docker-compose)
    POSTGRES_USER: str = "ghostmeter"
    POSTGRES_PASSWORD: str = "ghostmeter"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ghostmeter"

    # Modbus TCP
    MODBUS_HOST: str = "0.0.0.0"
    MODBUS_PORT: int = 502

    # Direct override (takes precedence if set)
    DATABASE_URL: str | None = None

    @computed_field
    @property
    def database_url_computed(self) -> str:
        """Build DATABASE_URL from individual vars, or use direct override."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()

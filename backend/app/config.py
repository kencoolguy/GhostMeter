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
    APP_VERSION: str = "0.4.0"
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

    # SNMP
    SNMP_PORT: int = 10161
    SNMP_COMMUNITY: str = "public"

    # OPC UA
    OPCUA_HOST: str = "0.0.0.0"
    OPCUA_PORT: int = 4840
    OPCUA_ENDPOINT_PATH: str = "/ghostmeter/server/"
    OPCUA_SERVER_NAME: str = "GhostMeter OPC UA Server"
    OPCUA_NAMESPACE_URI: str = "http://ghostmeter.local/opcua/"

    # BACnet/IP
    BACNET_ADDRESS: str = "0.0.0.0/0"  # CIDR; subnet mask needed for broadcast calc
    BACNET_PORT: int = 47808
    BACNET_DEVICE_INSTANCE_BASE: int = 100000  # device instance = base + slave_id; router = base
    BACNET_NETWORK: int = 100  # virtual (VLAN) network number

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

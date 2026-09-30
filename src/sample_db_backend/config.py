"""Environment-based application configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8010, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    public_hostname: str = Field(default="sbdb.animarium.ai", alias="PUBLIC_HOSTNAME")

    # NPÚ Geoportal layer root (…/FeatureServer/0) — docs/npu-geoportal-sync.md
    npu_layer_url: str | None = Field(default=None, alias="NPU_LAYER_URL")
    npu_layer_name: str | None = Field(default=None, alias="NPU_LAYER_NAME")
    npu_tag_fields: str | None = Field(
        default="TYP,KATEGORIE,DRUH,STATUS,TYP_PAM",
        alias="NPU_TAG_FIELDS",
    )
    npu_url_fields: str | None = Field(
        default="URL,ODKAZ,LINK,WWW",
        alias="NPU_URL_FIELDS",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()

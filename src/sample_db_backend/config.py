"""Environment-based application configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locked CP_UAP_PVO MapServer layer — docs/npu-geoportal-sync.md
_DEFAULT_NPU_LAYER_URL = (
    "https://geoportal.npu.cz/arcgis/rest/services/Tematicke/CP_UAP_PVO/MapServer/0"
)
_DEFAULT_NPU_TAG_FIELDS = (
    "Subtyp,typOchranyKod,typOchranyNazev,fazeOchranyKod,fazeOchranyNazev,PrStavNazev"
)
_DEFAULT_NPU_URL_FIELDS = "urlExt,urlInt"
_DEFAULT_NPU_TEMPORAL_FIELDS = "platn_od,platn_do,aktual,datumStavuOchrany"


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

    # NPÚ Geoportal MapServer layer root (…/MapServer/0) — docs/npu-geoportal-sync.md
    npu_layer_url: str | None = Field(default=_DEFAULT_NPU_LAYER_URL, alias="NPU_LAYER_URL")
    npu_layer_name: str | None = Field(default=None, alias="NPU_LAYER_NAME")
    npu_tag_fields: str | None = Field(
        default=_DEFAULT_NPU_TAG_FIELDS,
        alias="NPU_TAG_FIELDS",
    )
    npu_url_fields: str | None = Field(
        default=_DEFAULT_NPU_URL_FIELDS,
        alias="NPU_URL_FIELDS",
    )
    npu_temporal_fields: str | None = Field(
        default=_DEFAULT_NPU_TEMPORAL_FIELDS,
        alias="NPU_TEMPORAL_FIELDS",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()

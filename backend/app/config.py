from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database — accepts plain postgresql:// (Railway default) or postgresql+asyncpg://
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/zoning"

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, v: str) -> str:
        """Railway sets DATABASE_URL as postgresql:// — upgrade it to asyncpg automatically."""
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # Anthropic
    anthropic_api_key: str = ""

    # Optional data sources
    regrid_api_key: str = ""

    # Competition & saturation analysis
    google_places_api_key: str = ""
    competitor_sqft_default: int = 60_000
    saturation_threshold_low: float = 7.0    # sq ft/person — below = underserved (green)
    saturation_threshold_high: float = 10.0  # sq ft/person — above = oversupplied (red)
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # Public GIS services
    fema_nfhl_url: str = (
        "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
    )
    usfws_nwi_url: str = (
        # FWS MapServer at fws.gov returns 403; use AGOL-hosted FeatureServer instead
        "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Wetlands/FeatureServer"
    )
    usgs_3dep_dem_url: str = (
        "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
    )

    # CORS — comma-separated string; split into list at usage time
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for Alembic migrations."""
        return (
            self.database_url
            .replace("+asyncpg", "+psycopg2")
            .replace("+aiosqlite", "")
        )

    @property
    def regrid_enabled(self) -> bool:
        return bool(self.regrid_api_key)

    @property
    def google_places_enabled(self) -> bool:
        return bool(self.google_places_api_key)


settings = Settings()

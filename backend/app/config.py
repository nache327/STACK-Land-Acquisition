import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# Look in the backend dir AND the repo root, so the same .env works whether the
# process is launched from ./backend or from the repo root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_ENV_FILES = (str(_REPO_ROOT / ".env"), str(_BACKEND_DIR / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment label — "local", "dev", "prod", etc.
    environment: str = "local"

    # Database — REQUIRED. Must come from environment / .env. No local fallback:
    # Supabase is the single source of truth.
    database_url: str

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, v: str) -> str:
        """Supabase / Railway set DATABASE_URL as postgresql:// — upgrade to asyncpg."""
        if not v:
            raise ValueError("DATABASE_URL is not set. Configure it in .env or the process environment.")
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # Anthropic
    anthropic_api_key: str = ""

    # Optional data sources
    regrid_api_key: str = ""

    # Resend (transactional email). When unset the daily-digest worker
    # logs the rendered email instead of sending — useful for local dev
    # and as a safety net before RESEND_API_KEY is provisioned in prod.
    resend_api_key: str = ""
    resend_from_address: str = "ParcelLogic <alerts@parcellogic.com>"
    digest_dashboard_base_url: str = "https://zoning-finder.vercel.app"
    # Until per-user email lands, the digest worker sends to this address
    # for every email-enabled filter. Set in Railway env.
    digest_default_recipient: str = ""

    # Redis — REQUIRED. API + worker must use the SAME url for the queue to work.
    redis_url: str

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

    # Market saturation thresholds (sq ft of storage per person)
    saturation_threshold_low: float = 7.0   # below = underserved (green)
    saturation_threshold_high: float = 10.0  # above = oversupplied (red)
    competitor_sqft_default: int = 60000     # assumed sq ft when a facility has no sq_ft

    # Google Places (optional — enables competitor auto-fetch)
    google_places_api_key: str = ""

    @property
    def google_places_enabled(self) -> bool:
        return bool(self.google_places_api_key)

    # CORS — comma-separated string; split into list at usage time
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for Alembic migrations.
        Uses session-mode pooler (port 5432) because psycopg2 requires
        session-level features (hstore OID lookup) that break on port 6543.
        """
        return (
            self.database_url
            .replace("+asyncpg", "+psycopg2")
            .replace("+aiosqlite", "")
            .replace(":6543/", ":5432/")
        )

    @property
    def regrid_enabled(self) -> bool:
        return bool(self.regrid_api_key)

    @property
    def resend_enabled(self) -> bool:
        return bool(self.resend_api_key)

    @property
    def database_url_sanitized(self) -> str:
        return _sanitize_url(self.database_url)

    @property
    def redis_url_sanitized(self) -> str:
        return _sanitize_url(self.redis_url)


def _sanitize_url(url: str) -> str:
    """Strip credentials so URLs are safe to log."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            netloc = f"***@{host}" if host else "***"
            parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)
    except Exception:
        return re.sub(r"://[^@/]+@", "://***@", url)


settings = Settings()

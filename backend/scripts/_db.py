"""Shared DB DSN helper for backend/scripts/*.

NEVER hardcode credentials in a script. Read the DSN from the environment
(DATABASE_URL, loaded from backend/.env by pydantic settings). This module is the
single source of truth so a leaked-credential incident can't recur one script at a
time.

    from scripts._db import get_dsn, get_sync_dsn

    engine = create_async_engine(get_dsn())          # SQLAlchemy async form
    conn   = await asyncpg.connect(get_sync_dsn())    # asyncpg / session-mode 5432
"""
from __future__ import annotations

import os


def _raw() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        # pydantic settings loads backend/.env; scripts already import app.*
        try:
            from app.config import settings

            url = settings.database_url
        except Exception:  # pragma: no cover - fallback only
            url = None
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Put it in backend/.env or export it before "
            "running this script. Do NOT hardcode credentials."
        )
    return url


def get_dsn() -> str:
    """SQLAlchemy async DSN (postgresql+asyncpg://...)."""
    u = _raw()
    if u.startswith("postgresql+asyncpg://"):
        return u
    return u.replace("postgresql://", "postgresql+asyncpg://", 1)


def get_sync_dsn() -> str:
    """URL DSN for asyncpg.connect() / psycopg — session-mode port 5432, no +asyncpg.

    asyncpg.connect() and psycopg both accept this URL form (replacing the older
    libpq 'host=... password=...' keyword strings the scripts used to hardcode)."""
    return (
        _raw()
        .replace("postgresql+asyncpg://", "postgresql://", 1)
        .replace(":6543/", ":5432/")
    )

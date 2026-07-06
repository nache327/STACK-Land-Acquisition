"""
Shared test fixtures for the Zoning Finder backend.

Session-scoped fixtures create the database schema once per test run.
Test-scoped fixtures provide a clean session per test.
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base


# Substrings that mark a production / pooled Supabase DSN. The db_engine
# fixture runs Base.metadata.drop_all — pointing it at any of these would DROP
# THE PRODUCTION DATABASE. Refuse to run instead.
_PROD_DSN_MARKERS = ("supabase.com", "pooler", ":6543")


def _test_db_url() -> str:
    """Return the test DATABASE_URL, preferring an env override.

    Hard-fails if DATABASE_URL points at production: the schema fixtures below
    drop and recreate every table, so running the suite with a prod DSN in the
    environment (the common local setup, where backend/.env holds the live
    Supabase URL) would destroy production data. Fail loudly rather than run.
    """
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/zoning_test",
    )
    lowered = url.lower()
    if any(marker in lowered for marker in _PROD_DSN_MARKERS):
        raise RuntimeError(
            "Refusing to run the test suite against what looks like a PRODUCTION "
            "database (DATABASE_URL matches a Supabase/pooled DSN). The test "
            "fixtures drop_all + create_all every table. Point DATABASE_URL at a "
            "local/CI test database (e.g. the default localhost:5432/zoning_test) "
            "before running tests."
        )
    # Ensure we use asyncpg for async tests
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _bypass_admin_auth():
    """Suite-wide bypass of the shared-secret admin gate (require_secret).

    Router-level auth (2026-07-06) fail-closes with 503 when ADMIN_API_SECRET
    is unset — which is every CI/test environment — so any test exercising a
    gated admin/debug route would fail on auth instead of testing its actual
    behavior. Tests exercise route logic; the auth contract itself is pinned
    separately in tests/test_admin_auth.py (which pops this override for its
    end-to-end case).
    """
    from app.api._auth import require_secret
    from app.main import app

    app.dependency_overrides[require_secret] = lambda: None
    yield
    app.dependency_overrides.pop(require_secret, None)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine():
    """
    Session-scoped engine.  Creates all tables (including PostGIS extension)
    once before the test suite and tears them down after.

    loop_scope="session" is required with pytest-asyncio >=0.24 so the engine
    (and its connection pool) stays on the same event loop across all tests;
    otherwise function-scoped fixtures pulling on this engine raise
    RuntimeError: attached to a different loop.
    """
    url = _test_db_url()
    engine = create_async_engine(url, echo=False)

    # Enable PostGIS and create all tables
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine) -> AsyncSession:
    """
    Test-scoped session (function lifetime, session-scoped event loop).
    Each test runs inside a transaction that is rolled back at the end,
    so tests are isolated without truncating tables.
    """
    session_maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
        await session.rollback()

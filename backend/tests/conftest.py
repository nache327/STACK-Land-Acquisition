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


def _test_db_url() -> str:
    """Return the test DATABASE_URL, preferring an env override."""
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/zoning_test",
    )
    # Ensure we use asyncpg for async tests
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """
    Session-scoped engine.  Creates all tables (including PostGIS extension)
    once before the test suite and tears them down after.
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


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    """
    Test-scoped session.  Each test runs inside a transaction that is
    rolled back at the end, so tests are isolated without truncating tables.
    """
    session_maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
        await session.rollback()

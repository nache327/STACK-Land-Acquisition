import logging

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


logger.info("Connected to Postgres at %s (env=%s)", settings.database_url_sanitized, settings.environment)

# Supabase transaction-mode pooler (port 6543) does not pin connections, so
# asyncpg's prepared-statement cache must be disabled — otherwise a connection
# hands a stmt back to the pool and the next caller hits "prepared statement
# already exists". Session-mode (5432) is unaffected by these flags.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    # asyncpg-level cache (per-connection): turn off statement preparation.
    connect_args={
        "statement_cache_size": 0,
        # Force unique server-side prepared statement names so a stmt left on
        # one pooler-pinned conn can't collide on the next checkout.
        "prepared_statement_name_func": lambda: f"__asyncpg_{__import__('uuid').uuid4().hex}__",
    },
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

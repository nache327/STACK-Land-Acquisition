import logging

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


logger.info("Connected to Postgres at %s (env=%s)", settings.database_url_sanitized, settings.environment)

# NullPool: no SQLAlchemy-level connection pooling. Each request opens and closes
# its own connection. pgbouncer handles server-side pooling. This avoids zombie
# connections from rapid redeployments exhausting Supabase's session-mode limit,
# and avoids asyncio event-loop lock binding errors across worker threads.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
        # Per-command client-side timeout. Prevents asyncpg from hanging indefinitely
        # if the TCP connection to pgBouncer becomes half-open (no server-side response).
        # Also caps asyncpg's internal cancel-request cleanup after asyncio.timeout fires.
        "command_timeout": 90,
        # Request read-write mode in the asyncpg startup message. PgBouncer
        # transaction-mode can override this, so we also set postgresql_readonly=False
        # below to force BEGIN READ WRITE at the SQLAlchemy level.
        "server_settings": {"default_transaction_read_only": "off"},
    },
    # Force SQLAlchemy to emit BEGIN READ WRITE for every transaction so that
    # PgBouncer transaction-mode connections handed out in read-only state are
    # immediately promoted to read-write before any DML is attempted.
    execution_options={"postgresql_readonly": False},
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

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


async def _on_asyncpg_connect(connection) -> None:
    """asyncpg `init` hook — runs once per new pool connection.

    Why: pgBouncer transaction-mode pooling for Supabase sometimes returns a
    server connection whose session-level `default_transaction_read_only` was
    flipped to `on` by an earlier client. asyncpg's `server_settings` startup
    options don't reliably survive the pooler. This async callback runs as the
    first command on the brand-new pool connection — no greenlet context
    issues because asyncpg invokes it inside its own async setup.
    """
    await connection.execute("SET default_transaction_read_only = off")


def make_engine(database_url: str | None = None):
    """Build an AsyncEngine configured for Supabase pgBouncer + Dramatiq workers.

    Used by both the API process (one shared engine) and the worker actors
    (one fresh engine per task because asyncio locks can't cross
    asyncio.run() calls). Centralising this guarantees the read-only-flag
    workaround applies in both places.
    """
    return create_async_engine(
        database_url or settings.database_url,
        echo=False,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,
            # Per-command client-side timeout. Prevents asyncpg from hanging
            # if the TCP connection to pgBouncer becomes half-open. Also caps
            # asyncpg's internal cancel-request cleanup after asyncio.timeout.
            "command_timeout": 90,
            # Request read-write at the asyncpg startup level. The Supabase
            # pgBouncer transaction-mode pooler frequently strips startup
            # options, so we also force RW per-connection via the asyncpg
            # `init` callback below.
            "server_settings": {"default_transaction_read_only": "off"},
            # asyncpg `init` is invoked as a coroutine for every new connection
            # from inside asyncpg's own async setup — no SQLAlchemy greenlet
            # bridge needed (which was the failure mode of a sync `connect`
            # event handler).
            "init": _on_asyncpg_connect,
        },
    )


# NullPool: no SQLAlchemy-level connection pooling. Each request opens and closes
# its own connection. pgbouncer handles server-side pooling. This avoids zombie
# connections from rapid redeployments exhausting Supabase's session-mode limit,
# and avoids asyncio event-loop lock binding errors across worker threads.
engine = make_engine()

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

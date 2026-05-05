import logging

from sqlalchemy import event
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
        # Request read-write at the asyncpg startup level. The Supabase pgBouncer
        # transaction-mode pooler frequently strips startup options, so we also
        # force RW per-connection via the `connect` event below.
        "server_settings": {"default_transaction_read_only": "off"},
    },
)


@event.listens_for(engine.sync_engine, "connect")
def _force_read_write_on_connect(dbapi_conn, _connection_record):
    """Issue `SET default_transaction_read_only = off` on every new connection.

    Why: pgBouncer transaction-mode pooling for Supabase sometimes returns a
    server connection whose session-level `default_transaction_read_only` was
    flipped to `on` by an earlier client. asyncpg's `server_settings` startup
    options don't always survive the pooler. This is the belt-and-braces fix
    that runs the SET as the first command on the brand-new pool connection,
    independent of pgBouncer's startup-option handling.
    """
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("SET default_transaction_read_only = off")
    finally:
        cursor.close()

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

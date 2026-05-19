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


def make_engine(database_url: str | None = None, command_timeout: int = 90):
    """Build an AsyncEngine compatible with both the API process and Dramatiq workers.

    No `async_creator` — that path requires a greenlet context Dramatiq's
    `asyncio.run()` doesn't provide, and was the source of the
    `MissingGreenlet: greenlet_spawn has not been called` crash on every
    worker actor invocation.

    Per-connection setup (clear leftover prepared statements, force RW
    transactions) is wired up through SQLAlchemy's sync `connect` event
    listener registered just below — which runs in the correct context
    SQLAlchemy already manages for asyncpg's adapted DBAPI connection.

    `command_timeout` is the asyncpg client-side per-command timeout in
    seconds. Default 90s for the main engine. Audit-style operations that
    legitimately run for minutes (e.g. refresh_all_snapshots over big
    counties) should use the alternate engine built with a higher value.
    """
    url = database_url or settings.database_url
    new_engine = create_async_engine(
        url,
        echo=False,
        # NullPool: no SQLAlchemy-level connection pooling. Each request opens
        # and closes its own connection. The upstream Supabase Supavisor pooler
        # does the actual connection pooling. NullPool also avoids the asyncio
        # Lock-bound-to-event-loop crash when a Dramatiq worker thread tears
        # down its event loop and rebuilds it for the next task.
        poolclass=NullPool,
        pool_pre_ping=True,
        future=True,
        connect_args={
            # Required for transaction-mode pgBouncer compat. Harmless on
            # session-mode (5432) but kept as belt-and-braces.
            "statement_cache_size": 0,
            # Per-command client-side timeout so a half-open TCP connection
            # to the pooler can't hang a worker forever.
            "command_timeout": command_timeout,
            # asyncpg startup option — ignored by some pooler configurations,
            # so the `connect` listener below issues the SET explicitly.
            "server_settings": {"default_transaction_read_only": "off"},
        },
    )

    @event.listens_for(new_engine.sync_engine, "connect")
    def _set_connection_settings(dbapi_connection, _connection_record):
        """Run on every new pool connection, in SQLAlchemy's sync wrapper context.

        DEALLOCATE ALL: clears any prepared statements left on the underlying
            physical connection by a prior pooler tenant.
        SET default_transaction_read_only = off: counteracts a leaked session-level
            read-only flag from a prior client (e.g. an audit script that did
            `SET … = on` and the pooler reused the connection).
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("DEALLOCATE ALL")
            cursor.execute("SET default_transaction_read_only = off")
        finally:
            cursor.close()

    return new_engine


engine = make_engine()

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Long-running engine for operator-triggered batch operations like the
# coverage_audit refresh sweep — the audit SQL legitimately takes minutes
# on big counties (Middlesex MA 423k, Mont MD 281k, Mont PA 301k parcels).
# A separate engine with command_timeout=600 lets those complete; the
# default 90s engine is unchanged.
long_running_engine = make_engine(command_timeout=600)
long_running_session_maker = async_sessionmaker(
    long_running_engine,
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

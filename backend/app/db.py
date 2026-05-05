import logging
import uuid

import asyncpg
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


def _asyncpg_dsn(url: str) -> str:
    """Strip the SQLAlchemy `+asyncpg` dialect marker so asyncpg.connect accepts it."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _on_asyncpg_connect(connection: "asyncpg.Connection") -> None:
    """asyncpg `init` hook — runs once per new pool connection.

    Why: pgBouncer transaction-mode pooling for Supabase sometimes returns a
    server connection whose session-level `default_transaction_read_only` was
    flipped to `on` by an earlier client. asyncpg's `server_settings` startup
    options don't reliably survive the pooler. This async callback runs as the
    first command on the brand-new pool connection — no greenlet context
    issues because asyncpg invokes it inside its own async setup.
    """
    await connection.execute("SET default_transaction_read_only = off")


def _make_async_creator(database_url: str):
    """Return an async creator coroutine that calls asyncpg.connect directly.

    `init=` is an `asyncpg.create_pool()` parameter, NOT `asyncpg.connect()`.
    Since we use SQLAlchemy's pool (NullPool) and not asyncpg's pool, we
    must run the SET as an explicit statement on the brand-new connection
    after asyncpg.connect() returns.
    """
    dsn = _asyncpg_dsn(database_url)

    async def _create_conn() -> "asyncpg.Connection":
        conn = await asyncpg.connect(
            dsn,
            statement_cache_size=0,
            command_timeout=90,
            server_settings={"default_transaction_read_only": "off"},
            # pgBouncer transaction-mode pooling reuses physical connections
            # across logical sessions. asyncpg's default prepared-statement
            # name pool (`__asyncpg_stmt_NN__`) collides when one client
            # prepared a statement, was released back to the pool, and the
            # next client tries to prepare the same name — raising
            # DuplicatePreparedStatementError. Random per-statement names
            # remove the collision surface.
            prepared_statement_name_func=lambda: f"__asyncpg_{uuid.uuid4().hex}__",
        )
        # Belt-and-braces: pgBouncer transaction-mode pooling for Supabase
        # frequently strips startup options, so issue the SET explicitly on
        # the connection before handing it to SQLAlchemy. This runs inside
        # the asyncpg connection's own async context — no greenlet bridge.
        await _on_asyncpg_connect(conn)
        return conn

    return _create_conn


def make_engine(database_url: str | None = None):
    """Build an AsyncEngine configured for Supabase pgBouncer + Dramatiq workers.

    Used by both the API process (one shared engine) and the worker actors
    (one fresh engine per task because asyncio locks can't cross
    asyncio.run() calls). Centralising this guarantees the read-only-flag
    workaround applies in both places.
    """
    url = database_url or settings.database_url
    return create_async_engine(
        url,
        echo=False,
        poolclass=NullPool,
        async_creator=_make_async_creator(url),
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

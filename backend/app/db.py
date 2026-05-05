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
    """Reset known per-connection state inherited from a pgBouncer pool slot.

    Two pieces of leakage to neutralise on every new connection:

    1. `default_transaction_read_only` may be `on` from a prior client's
       session-level SET (e.g. an audit script that did `SET … = on`).
       asyncpg's `server_settings` startup option doesn't reliably survive
       pgBouncer transaction-mode, so issue the SET explicitly.

    2. Prepared statements with names like `__asyncpg_stmt_NN__` may already
       exist on the underlying physical connection from a prior asyncpg
       client. The next PREPARE of the same name would raise
       `DuplicatePreparedStatementError`. `DEALLOCATE ALL` releases all
       named prepared statements on the connection so our subsequent
       PREPAREs use clean names.
    """
    # Combined into one simple-query call so the DEALLOCATE itself doesn't
    # need to PREPARE anything against the polluted name set.
    await connection.execute(
        "DEALLOCATE ALL; SET default_transaction_read_only = off"
    )


def _make_async_creator(database_url: str):
    """Return an async creator coroutine that calls asyncpg.connect directly.

    `init=` is an `asyncpg.create_pool()` parameter, NOT `asyncpg.connect()`.
    Since we use SQLAlchemy's pool (NullPool) and not asyncpg's pool, we
    must run the SET as an explicit statement on the brand-new connection
    after asyncpg.connect() returns.
    """
    dsn = _asyncpg_dsn(database_url)

    async def _create_conn() -> "asyncpg.Connection":
        # NB: asyncpg.connect() doesn't accept `prepared_statement_name_func`
        # (only the asyncpg.create_pool wrapper does). The real fix for the
        # DuplicatePreparedStatementError class of bugs is to use Supabase's
        # session-mode pooler (port 5432) instead of transaction-mode (port
        # 6543) — set DATABASE_URL accordingly in deploy env. The asyncpg
        # kwargs below are still useful for the session-mode case.
        conn = await asyncpg.connect(
            dsn,
            statement_cache_size=0,
            command_timeout=90,
            server_settings={"default_transaction_read_only": "off"},
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

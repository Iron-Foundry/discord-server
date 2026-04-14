"""PostgreSQL async engine + session factory for discord-server."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(dsn: str) -> None:
    """Initialise the async engine and session factory from a DATABASE_URL DSN."""
    global _engine, _session_factory
    _engine = create_async_engine(dsn, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info("PostgreSQL connection pool initialised")


async def close_db() -> None:
    """Dispose the engine and release all connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("PostgreSQL connection pool closed")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-level session factory. Raises if init_db not called."""
    if _session_factory is None:
        raise RuntimeError("init_db() has not been called")
    return _session_factory

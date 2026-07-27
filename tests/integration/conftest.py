"""Real-Postgres fixtures for discord-server repository tests.

Spins up a throwaway Postgres container and builds the schema directly from the
ORM metadata (the bot shares api-backend's tables but has no Alembic of its
own). Selected only under `-m integration`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.models import Base

pytestmark = pytest.mark.integration

_docker = pytest.importorskip("docker")
_tc_postgres = pytest.importorskip("testcontainers.postgres")


def _docker_available() -> bool:
    try:
        _docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def _pg_dsn() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("Docker is not available for integration tests")
    postgres = _tc_postgres.PostgresContainer("postgres:17-alpine", driver="asyncpg")
    postgres.start()
    try:
        yield postgres.get_connection_url()
    finally:
        postgres.stop()


@pytest.fixture
async def session_factory(
    _pg_dsn: str,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(_pg_dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

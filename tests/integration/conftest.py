"""Real-Postgres fixtures for discord-server repository tests.

The Postgres instance comes from the test runner (`TEST_DATABASE_URL`, one
container shared by every module) when it supplies one, and from a throwaway
testcontainer otherwise, so a hand-run `uv run pytest -m integration` still
works. Either way this suite carves out its own database so it never races the
api-backend suite running beside it.

The bot shares api-backend's tables but has no Alembic of its own, so the schema
is built straight from the ORM metadata - once per worker, with the tables
emptied between tests rather than dropped and recreated.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
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


def _with_database(url: str, name: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


def _async_url(url: str) -> str:
    if "+asyncpg" in url:
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _truncate_statement() -> str:
    targets = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    return f"TRUNCATE TABLE {targets} RESTART IDENTITY CASCADE"


@pytest.fixture(scope="session")
def _base_dsn() -> Iterator[str]:
    runner_dsn = os.getenv("TEST_DATABASE_URL")
    if runner_dsn:
        yield _async_url(runner_dsn)
        return

    if not _docker_available():
        pytest.skip("Docker is not available for integration tests")
    postgres = _tc_postgres.PostgresContainer("postgres:17-alpine", driver="asyncpg")
    postgres.start()
    try:
        yield postgres.get_connection_url()
    finally:
        postgres.stop()


@pytest.fixture(scope="session")
async def _engine(_base_dsn: str, worker_id: str) -> AsyncGenerator[AsyncEngine]:
    suffix = "" if worker_id == "master" else f"_{worker_id}"
    name = f"discord_server_test{suffix}"

    admin = create_async_engine(
        _with_database(_base_dsn, "postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin.connect() as conn:
            await conn.execute(
                sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            )
            await conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    finally:
        await admin.dispose()

    engine = create_async_engine(_with_database(_base_dsn, name))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(
    _engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    async with _engine.begin() as conn:
        await conn.execute(sa.text(_truncate_statement()))
    yield async_sessionmaker(_engine, expire_on_commit=False)

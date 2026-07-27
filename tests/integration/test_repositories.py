"""Repositories exercised against a real Postgres, not mocks."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import Config
from features.action_log.models import ActionLogConfig
from features.action_log.pg_repository import PgActionLogRepository
from features.broadcast.models import BroadcastConfig
from features.broadcast.pg_repository import PgBroadcastRepository

pytestmark = pytest.mark.integration

_GUILD = 4242


async def test_broadcast_config_round_trip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgBroadcastRepository(session_factory)

    assert await repo.get_config(_GUILD) is None

    await repo.save_config(BroadcastConfig(guild_id=_GUILD, role_id=777))
    loaded = await repo.get_config(_GUILD)
    assert loaded is not None
    assert loaded.role_id == 777

    # Upsert overwrites in place rather than duplicating the row.
    await repo.save_config(BroadcastConfig(guild_id=_GUILD, role_id=888))
    loaded = await repo.get_config(_GUILD)
    assert loaded is not None
    assert loaded.role_id == 888

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Config).where(
                        Config.guild_id == _GUILD, Config.key == "broadcast"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1


async def test_action_log_and_broadcast_isolated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two repos keyed off the same config table must not clobber each other."""
    broadcast = PgBroadcastRepository(session_factory)
    action_log = PgActionLogRepository(session_factory)

    await broadcast.save_config(BroadcastConfig(guild_id=_GUILD, role_id=1))
    await action_log.save_config(ActionLogConfig(guild_id=_GUILD))

    saved = await broadcast.get_config(_GUILD)
    assert saved is not None
    assert saved.role_id == 1
    assert await action_log.get_config(_GUILD) is not None

    async with session_factory() as session:
        keys = (
            (await session.execute(select(Config.key).where(Config.guild_id == _GUILD)))
            .scalars()
            .all()
        )
    assert set(keys) == {"broadcast", "action_log"}

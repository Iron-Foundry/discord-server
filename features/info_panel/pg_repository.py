"""PostgreSQL persistence for the info panel state (message IDs)."""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import Config
from features.info_panel.models import InfoPanelConfig, InfoPanelState

_CONFIG_KEY = "info_panel_config"
_STATE_KEY = "info_panel_state"
_GLOBAL_GUILD_ID = 0
_GUILD_ID = int(os.getenv("GUILD_ID", "0"))


class PgInfoPanelRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def get_panel_config(self) -> InfoPanelConfig:
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == _GLOBAL_GUILD_ID,
                    Config.key == _CONFIG_KEY,
                )
            )
            data = result.scalar_one_or_none() or {}
        if not data:
            return InfoPanelConfig()
        return InfoPanelConfig.model_validate(data)

    async def get_panel_state(self) -> InfoPanelState:
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == _GUILD_ID,
                    Config.key == _STATE_KEY,
                )
            )
            data = result.scalar_one_or_none() or {}
        if not data:
            return InfoPanelState()
        return InfoPanelState.model_validate(data)

    async def save_panel_state(self, state: InfoPanelState) -> None:
        value = state.model_dump()
        async with self._factory() as session:
            await session.execute(
                pg_insert(Config)
                .values(guild_id=_GUILD_ID, key=_STATE_KEY, value=value)
                .on_conflict_do_update(
                    index_elements=["guild_id", "key"],
                    set_={"value": value},
                )
            )
            await session.commit()

    async def clear_panel_state(self) -> None:
        from sqlalchemy import delete

        async with self._factory() as session:
            await session.execute(
                delete(Config).where(
                    Config.guild_id == _GUILD_ID,
                    Config.key == _STATE_KEY,
                )
            )
            await session.commit()

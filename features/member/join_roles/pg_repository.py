from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import Config
from features.member.join_roles.models import JoinRoleConfig

_KEY = "join_roles"


class PgJoinRoleRepository:
    """PostgreSQL persistence for the join role service."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def ensure_indexes(self) -> None:
        """No-op - indexes are managed by Alembic migrations."""
        logger.info("PgJoinRoleRepository: ready")

    async def get_config(self, guild_id: int) -> JoinRoleConfig | None:
        """Return the join role config for the guild, or None if not configured."""
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == guild_id, Config.key == _KEY
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                logger.debug("PgJoinRoleRepository: no config for guild {}", guild_id)
                return None
            try:
                config = JoinRoleConfig.model_validate({**row, "guild_id": guild_id})
                logger.debug(
                    "PgJoinRoleRepository: loaded config for guild {}", guild_id
                )
                return config
            except Exception as exc:
                logger.error(
                    "PgJoinRoleRepository: failed to parse config for guild {}: {}",
                    guild_id,
                    exc,
                )
                return None

    async def save_config(self, config: JoinRoleConfig) -> None:
        """Upsert the join role config for the guild."""
        value = config.model_dump(mode="json", exclude={"guild_id"})
        stmt = (
            pg_insert(Config)
            .values(guild_id=config.guild_id, key=_KEY, value=value)
            .on_conflict_do_update(
                index_elements=["guild_id", "key"],
                set_={"value": value},
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()
        logger.debug("PgJoinRoleRepository: saved config for guild {}", config.guild_id)

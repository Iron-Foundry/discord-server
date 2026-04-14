from __future__ import annotations

from datetime import datetime, timezone

import discord
from loguru import logger
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import User
from features.user_keys.models import UserKey


class PgUserKeyRepository:
    """PostgreSQL persistence for per-user API keys."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def ensure_indexes(self) -> None:
        """No-op — indexes are managed by Alembic migrations."""
        logger.info("PgUserKeyRepository: ready")

    async def get_by_user(self, discord_user_id: int) -> UserKey | None:
        """Return the active key for a user, or None if they have none."""
        async with self._factory() as session:
            result = await session.execute(
                select(User).where(
                    User.discord_user_id == discord_user_id,
                    User.key_is_active == True,  # noqa: E712
                )
            )
            row = result.scalar_one_or_none()
            if row is None or row.api_key is None:
                return None
            return UserKey(
                discord_user_id=row.discord_user_id,
                discord_username=row.discord_username,
                guild_id=row.guild_id,
                guild_name="",
                key=row.api_key,
                is_active=row.key_is_active,
                created_at=row.key_created_at or row.created_at,
            )

    async def save(self, user_key: UserKey) -> None:
        """Upsert a user key, replacing any existing key for that user."""
        now = datetime.now(timezone.utc)
        async with self._factory() as session:
            await session.execute(
                update(User)
                .where(User.discord_user_id == user_key.discord_user_id)
                .values(
                    api_key=user_key.key,
                    key_is_active=user_key.is_active,
                    key_created_at=user_key.created_at,
                    discord_username=user_key.discord_username,
                    guild_id=user_key.guild_id,
                    updated_at=now,
                )
            )
            await session.commit()

    async def upsert_user_profile(self, user_key: UserKey) -> None:
        """Create or refresh the unified user profile for this user key."""
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(User)
            .values(
                discord_user_id=user_key.discord_user_id,
                discord_username=user_key.discord_username,
                guild_id=user_key.guild_id,
                api_key=user_key.key,
                key_is_active=user_key.is_active,
                key_created_at=user_key.created_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["discord_user_id"],
                set_={
                    "discord_username": user_key.discord_username,
                    "guild_id": user_key.guild_id,
                    "updated_at": now,
                },
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def get_user_profile(self, discord_user_id: int) -> dict | None:
        """Return the user profile as a dict, or None if not found."""
        async with self._factory() as session:
            result = await session.execute(
                select(User).where(User.discord_user_id == discord_user_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            d = {c.key: getattr(row, c.key) for c in User.__table__.columns}
            d.pop("_sa_instance_state", None)
            return d

    async def link_rsn(self, discord_user_id: int, rsn: str) -> None:
        """Set the RSN on a user profile."""
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(User)
            .values(
                discord_user_id=discord_user_id,
                discord_username="",
                guild_id=0,
                rsn=rsn,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["discord_user_id"],
                set_={"rsn": rsn, "updated_at": now},
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def upsert_member(self, member: discord.Member) -> None:
        """Insert a bare user profile for a guild member, preserving existing RSN."""
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(User)
            .values(
                discord_user_id=member.id,
                discord_username=str(member),
                guild_id=member.guild.id,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["discord_user_id"],
                set_={
                    "discord_username": str(member),
                    "guild_id": member.guild.id,
                    "updated_at": now,
                },
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def delete_user(self, discord_user_id: int) -> None:
        """Delete a user profile and all associated data."""
        async with self._factory() as session:
            await session.execute(
                delete(User).where(User.discord_user_id == discord_user_id)
            )
            await session.commit()

    async def set_stats_opt_out(self, discord_user_id: int, opt_out: bool) -> None:
        """Set or clear the stats opt-out flag on a user profile."""
        now = datetime.now(timezone.utc)
        stmt = (
            pg_insert(User)
            .values(
                discord_user_id=discord_user_id,
                discord_username="",
                guild_id=0,
                stats_opt_out=opt_out,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["discord_user_id"],
                set_={"stats_opt_out": opt_out, "updated_at": now},
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

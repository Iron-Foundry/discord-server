from __future__ import annotations

from datetime import datetime, timezone

import discord
from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import User, UserAccount
from features.user_keys.models import UserKey


class PgUserKeyRepository:
    """PostgreSQL persistence for per-user API keys."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def ensure_indexes(self) -> None:
        """No-op - indexes are managed by Alembic migrations."""
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
        """Set the primary RSN on a user profile.

        Demotes any existing primary to alt, then upserts the new RSN as primary.
        """
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
            await self._upsert_primary_account(session, discord_user_id, rsn)
            await session.commit()

    async def _upsert_primary_account(
        self, session: AsyncSession, discord_user_id: int, rsn: str
    ) -> None:
        """Demote current primary to alt and set rsn as new primary in user_accounts."""
        now = datetime.now(timezone.utc)

        await session.execute(
            update(UserAccount)
            .where(
                UserAccount.discord_user_id == discord_user_id,
                UserAccount.is_primary == True,  # noqa: E712
            )
            .values(is_primary=False)
        )

        existing = await session.execute(
            select(UserAccount.id).where(
                UserAccount.discord_user_id == discord_user_id,
                func.lower(UserAccount.rsn) == rsn.lower(),
            )
        )
        if existing.scalar_one_or_none():
            await session.execute(
                update(UserAccount)
                .where(
                    UserAccount.discord_user_id == discord_user_id,
                    func.lower(UserAccount.rsn) == rsn.lower(),
                )
                .values(is_primary=True)
            )
        else:
            await session.execute(
                pg_insert(UserAccount).values(
                    discord_user_id=discord_user_id,
                    rsn=rsn,
                    is_primary=True,
                    created_at=now,
                )
            )

    async def get_user_accounts(self, discord_user_id: int) -> list[dict]:
        """Return all RSN accounts linked to a user, primary first."""
        async with self._factory() as session:
            result = await session.execute(
                select(UserAccount)
                .where(UserAccount.discord_user_id == discord_user_id)
                .order_by(UserAccount.is_primary.desc(), UserAccount.created_at.asc())
            )
            return [
                {
                    "id": row.id,
                    "rsn": row.rsn,
                    "is_primary": row.is_primary,
                }
                for row in result.scalars()
            ]

    async def add_account(self, discord_user_id: int, rsn: str) -> str | None:
        """Add an alt RSN. Returns an error message string on failure, None on success."""
        async with self._factory() as session:
            # Global uniqueness check
            conflict = await session.execute(
                select(UserAccount.discord_user_id).where(
                    func.lower(UserAccount.rsn) == rsn.lower()
                )
            )
            conflict_owner = conflict.scalar_one_or_none()
            if conflict_owner == discord_user_id:
                return "You already have that RSN linked."
            if conflict_owner is not None:
                return "That RSN is already linked. If this is your account, contact staff."

            # Cap check
            cap = await session.execute(
                select(func.count())
                .select_from(UserAccount)
                .where(UserAccount.discord_user_id == discord_user_id)
            )
            if (cap.scalar_one() or 0) >= 5:
                return (
                    "You've reached the 5-account limit."
                    " Remove an alt at ironfoundry.cc/members/settings first."
                )

            now = datetime.now(timezone.utc)

            # Check if user has any accounts (to determine is_primary)
            count_result = await session.execute(
                select(func.count())
                .select_from(UserAccount)
                .where(UserAccount.discord_user_id == discord_user_id)
            )
            is_first = (count_result.scalar_one() or 0) == 0

            await session.execute(
                pg_insert(UserAccount).values(
                    discord_user_id=discord_user_id,
                    rsn=rsn,
                    is_primary=is_first,
                    created_at=now,
                )
            )

            if is_first:
                await session.execute(
                    update(User)
                    .where(User.discord_user_id == discord_user_id)
                    .values(rsn=rsn, updated_at=now)
                )

            await session.commit()
            return None

    async def set_primary_account(self, discord_user_id: int, rsn: str) -> str | None:
        """Promote an RSN to primary. Returns error message or None on success."""
        async with self._factory() as session:
            row_result = await session.execute(
                select(UserAccount).where(
                    UserAccount.discord_user_id == discord_user_id,
                    func.lower(UserAccount.rsn) == rsn.lower(),
                )
            )
            row = row_result.scalar_one_or_none()
            if not row:
                return "That RSN is not linked to your account."

            if row.is_primary:
                return None

            now = datetime.now(timezone.utc)
            await session.execute(
                update(UserAccount)
                .where(
                    UserAccount.discord_user_id == discord_user_id,
                    UserAccount.is_primary == True,  # noqa: E712
                )
                .values(is_primary=False)
            )
            await session.execute(
                update(UserAccount)
                .where(UserAccount.id == row.id)
                .values(is_primary=True)
            )
            await session.execute(
                update(User)
                .where(User.discord_user_id == discord_user_id)
                .values(rsn=row.rsn, updated_at=now)
            )
            await session.commit()
            return None

    async def remove_account(self, discord_user_id: int, rsn: str) -> str | None:
        """Remove a linked RSN. Returns error message or None on success."""
        async with self._factory() as session:
            row_result = await session.execute(
                select(UserAccount).where(
                    UserAccount.discord_user_id == discord_user_id,
                    func.lower(UserAccount.rsn) == rsn.lower(),
                )
            )
            row = row_result.scalar_one_or_none()
            if not row:
                return "That RSN is not linked to your account."

            count_result = await session.execute(
                select(func.count())
                .select_from(UserAccount)
                .where(UserAccount.discord_user_id == discord_user_id)
            )
            total = count_result.scalar_one() or 0

            if row.is_primary and total > 1:
                return (
                    "Cannot remove your primary RSN while other accounts are linked."
                    " Set a different primary first."
                )

            now = datetime.now(timezone.utc)
            if total == 1:
                await session.execute(
                    update(User)
                    .where(User.discord_user_id == discord_user_id)
                    .values(rsn=None, updated_at=now)
                )

            await session.execute(delete(UserAccount).where(UserAccount.id == row.id))
            await session.commit()
            return None

    async def upsert_member(self, member: discord.Member) -> None:
        """Insert a bare user profile for a guild member, preserving existing RSN."""
        now = datetime.now(timezone.utc)
        joined_at = member.joined_at or now
        role_names = [r.name for r in member.roles if r.name != "@everyone"]
        async with self._factory() as session:
            result = await session.execute(
                update(User)
                .where(User.discord_user_id == member.id)
                .values(
                    discord_username=str(member),
                    discord_avatar_url=str(member.display_avatar.url),
                    guild_id=member.guild.id,
                    discord_roles=role_names,
                    join_date=joined_at,
                    updated_at=now,
                )
                .returning(User.discord_user_id)
            )
            if result.scalar_one_or_none() is None:
                await session.execute(
                    pg_insert(User).values(
                        discord_user_id=member.id,
                        discord_username=str(member),
                        discord_avatar_url=str(member.display_avatar.url),
                        guild_id=member.guild.id,
                        discord_roles=role_names,
                        join_date=joined_at,
                        created_at=joined_at,
                        updated_at=now,
                    )
                )
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

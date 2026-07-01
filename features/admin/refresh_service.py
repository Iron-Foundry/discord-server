"""Bulk refresh of discord_roles and clan_rank for all linked users."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import discord
from loguru import logger
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import Config, User


@dataclass
class RefreshResult:
    updated: int = 0
    skipped_not_in_guild: int = 0
    errors: int = 0


async def _load_wom_ranks(session: AsyncSession) -> dict[str, str]:
    rows = await session.execute(text("SELECT rsn, clan_rank FROM wom_clan_ranks"))
    return {row[0]: row[1] for row in rows}


async def _load_co_owner_role_id(guild: discord.Guild) -> str | None:
    role = discord.utils.get(guild.roles, name="Co-owner")
    return str(role.id) if role else None


async def _load_clan_rank_role_map(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == 0, Config.key == "clan_rank_mappings"
        )
    )
    cfg = result.scalar_one_or_none() or {}
    role_to_rank: dict[str, str] = {}
    for m in cfg.get("mappings", []):
        role_id = m.get("discord_role_id") or m.get("discord_role")
        clan_rank = m.get("clan_rank")
        if role_id and clan_rank:
            role_to_rank[str(role_id)] = clan_rank
    return role_to_rank


def _member_role_ids(
    member: discord.Member,
    guild: discord.Guild,
    co_owner_role_id: str | None,
) -> list[str]:
    ids = [str(r.id) for r in member.roles if r.name != "@everyone"]
    if member.id == guild.owner_id and co_owner_role_id and co_owner_role_id not in ids:
        ids.append(co_owner_role_id)
    return ids


async def refresh_all_roles(
    guild: discord.Guild,
    session_factory: async_sessionmaker[AsyncSession],
    dry_run: bool,
) -> RefreshResult:
    """Update discord_roles and clan_rank for every user currently in the guild.

    Reads role IDs directly from the gateway-cached member list. Derives
    clan_rank from wom_clan_ranks by RSN when available, falling back to
    the clan_rank_mappings config to infer from Discord roles.
    """
    result = RefreshResult()
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        wom_ranks = await _load_wom_ranks(session)
        role_to_rank = await _load_clan_rank_role_map(session)
        co_owner_role_id = await _load_co_owner_role_id(guild)

        rows = await session.execute(select(User.discord_user_id, User.rsn))
        users = [(row[0], row[1]) for row in rows]

    for discord_user_id, rsn in users:
        member = guild.get_member(discord_user_id)
        if member is None:
            result.skipped_not_in_guild += 1
            continue

        role_ids = _member_role_ids(member, guild, co_owner_role_id)

        clan_rank: str | None = None
        if rsn:
            clan_rank = wom_ranks.get(rsn.lower())
        if clan_rank is None:
            for rid in role_ids:
                if rid in role_to_rank:
                    clan_rank = role_to_rank[rid]
                    break

        if dry_run:
            logger.debug(
                "admin/refresh [dry]: {} -> roles={} rank={}",
                member,
                role_ids,
                clan_rank,
            )
            result.updated += 1
            continue

        try:
            async with session_factory() as session:
                values: dict = {"discord_roles": role_ids, "updated_at": now}
                if clan_rank is not None:
                    values["clan_rank"] = clan_rank
                await session.execute(
                    update(User)
                    .where(User.discord_user_id == discord_user_id)
                    .values(**values)
                )
                await session.commit()
            result.updated += 1
        except Exception as exc:
            logger.error(
                "admin/refresh: failed to update user {}: {}", discord_user_id, exc
            )
            result.errors += 1

    logger.info(
        "admin/refresh: updated={} skipped={} errors={}",
        result.updated,
        result.skipped_not_in_guild,
        result.errors,
    )
    return result

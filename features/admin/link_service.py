"""Auto-link Discord members to WOM-registered RSNs by display name match."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord
import httpx
from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import Config, User, UserAccount

_WOM_BASE = "https://api.wiseoldman.net/v2"
_WOM_API_KEY = os.getenv("WOM_API_KEY")


@dataclass
class LinkResult:
    linked: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _build_member_lookups(
    guild: discord.Guild,
) -> tuple[dict[str, discord.Member], dict[str, discord.Member]]:
    by_display: dict[str, discord.Member] = {}
    by_nick: dict[str, discord.Member] = {}
    for member in guild.members:
        by_display[member.display_name.lower()] = member
        if member.nick:
            by_nick[member.nick.lower()] = member
    return by_display, by_nick


async def _fetch_wom_history(rsn: str) -> list[str]:
    headers = {"X-Api-Key": _WOM_API_KEY} if _WOM_API_KEY else {}
    try:
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            resp = await client.get(f"{_WOM_BASE}/players/{rsn}/names")
            if resp.is_success:
                return [
                    c["oldName"] for c in resp.json() if c.get("status") == "approved"
                ]
    except Exception as exc:
        logger.warning(
            "admin/link: WOM name history fetch failed for {!r}: {}", rsn, exc
        )
    return []


async def _get_rank_role_id(session: AsyncSession, clan_rank: str) -> int | None:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == 0, Config.key == "clan_rank_mappings"
        )
    )
    cfg = result.scalar_one_or_none() or {}
    for m in cfg.get("mappings", []):
        if m.get("clan_rank") == clan_rank:
            raw = m.get("discord_role_id") or m.get("discord_role")
            return int(raw) if raw else None
    return None


async def _write_and_backfill(
    session: AsyncSession,
    member: discord.Member,
    rsn: str,
    clan_rank: str,
) -> None:
    now = datetime.now(timezone.utc)
    await session.execute(
        pg_insert(User)
        .values(
            discord_user_id=member.id,
            discord_username=str(member),
            discord_avatar_url=str(member.display_avatar.url),
            guild_id=member.guild.id,
            rsn=rsn,
            clan_rank=clan_rank,
            join_date=member.joined_at,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["discord_user_id"],
            set_={
                "rsn": rsn,
                "clan_rank": clan_rank,
                "discord_username": str(member),
                "discord_avatar_url": str(member.display_avatar.url),
                "updated_at": now,
            },
            where=User.rsn.is_(None),
        )
    )
    await session.execute(
        pg_insert(UserAccount).values(
            discord_user_id=member.id, rsn=rsn, is_primary=True, created_at=now
        )
    )
    ua_result = await session.execute(
        select(UserAccount.id).where(
            UserAccount.discord_user_id == member.id,
            func.lower(UserAccount.rsn) == rsn.lower(),
        )
    )
    ua_id = ua_result.scalar_one()

    history = await _fetch_wom_history(rsn)
    if history:
        await session.execute(
            text("UPDATE user_accounts SET rsn_history = :h WHERE id = :uid"),
            {"h": history, "uid": ua_id},
        )

    lower_rsns = [r.lower() for r in ([rsn] + history)]
    await session.execute(
        text(
            "UPDATE events SET user_id = :did, user_account_id = :ua "
            "WHERE replace(lower(player_name), chr(160), ' ') = ANY(:rsns)"
        ),
        {"did": member.id, "ua": ua_id, "rsns": lower_rsns},
    )
    await session.execute(
        text(
            "UPDATE coffer_events SET user_account_id = :ua WHERE lower(player_name) = ANY(:rsns)"
        ),
        {"ua": ua_id, "rsns": lower_rsns},
    )
    await session.execute(
        text(
            "UPDATE membership_events SET user_account_id = :ua WHERE lower(player_name) = ANY(:rsns)"
        ),
        {"ua": ua_id, "rsns": lower_rsns},
    )


async def auto_link_members(
    guild: discord.Guild,
    session_factory: async_sessionmaker[AsyncSession],
    dry_run: bool,
) -> LinkResult:
    """Match Discord members to WOM clan members by display name and link them.

    Skips any member already linked or any RSN already claimed. When dry_run
    is True, returns a preview with no writes or role assignments.
    """
    result = LinkResult()
    by_display, by_nick = _build_member_lookups(guild)
    role_cache: dict[str, int | None] = {}

    async with session_factory() as session:
        wom_rows = await session.execute(
            text("SELECT rsn, clan_rank FROM wom_clan_ranks")
        )
        wom_members = [(row[0], row[1]) for row in wom_rows]

        for rsn, clan_rank in wom_members:
            rsn_taken = await session.execute(
                select(UserAccount.id).where(func.lower(UserAccount.rsn) == rsn.lower())
            )
            if rsn_taken.scalar_one_or_none() is not None:
                result.skipped.append(f"{rsn}: RSN already linked")
                continue

            member = by_display.get(rsn.lower()) or by_nick.get(rsn.lower())
            if member is None:
                result.skipped.append(f"{rsn}: no Discord name match")
                continue

            already = await session.execute(
                select(func.count())
                .select_from(UserAccount)
                .where(UserAccount.discord_user_id == member.id)
            )
            if (already.scalar_one() or 0) > 0:
                result.skipped.append(f"{rsn}: {member} already has linked accounts")
                continue

            label = f"{rsn} -> {member} [{clan_rank}]"
            if dry_run:
                result.linked.append(label)
                continue

            try:
                await _write_and_backfill(session, member, rsn, clan_rank)

                if clan_rank not in role_cache:
                    role_cache[clan_rank] = await _get_rank_role_id(session, clan_rank)
                role_id = role_cache[clan_rank]

                await session.commit()

                if role_id is not None:
                    role = guild.get_role(role_id)
                    if role is not None:
                        await member.add_roles(role, reason="auto-link: WOM name match")

                result.linked.append(label)
                logger.info(
                    "admin/link: linked {} ({}) -> {!r} [{}]",
                    member,
                    member.id,
                    rsn,
                    clan_rank,
                )
            except Exception as exc:
                await session.rollback()
                result.errors.append(f"{rsn}: {exc}")
                logger.error("admin/link: failed to link {!r}: {}", rsn, exc)

    return result

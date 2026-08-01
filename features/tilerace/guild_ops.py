"""Single-object guild operations, each safe to call when the object is gone."""

from __future__ import annotations

import contextlib

import discord
from loguru import logger

from . import naming, overwrites, perms

_REASON = "Tile race provisioning"


async def ensure_role(
    guild: discord.Guild, role_id: int | None, name: str
) -> discord.Role:
    """Fetch the role by id and rename it, or create it when it is missing."""
    role = guild.get_role(role_id) if role_id else None
    if role is None:
        return await guild.create_role(name=name, mentionable=True, reason=_REASON)
    if role.name != name:
        await role.edit(name=name, reason=_REASON)
    return role


async def ensure_category(
    guild: discord.Guild, category_id: int | None, name: str, staff: discord.Role | None
) -> discord.CategoryChannel:
    existing = guild.get_channel(category_id) if category_id else None
    if isinstance(existing, discord.CategoryChannel):
        if existing.name != name:
            await existing.edit(name=name, reason=_REASON)
        return existing
    return await guild.create_category(
        name, overwrites=overwrites.category(guild, staff), reason=_REASON
    )


async def ensure_text_channel(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    channel_id: int | None,
    name: str,
    role: discord.Role,
    staff: discord.Role | None,
    toggles: dict[str, bool] | None = None,
) -> discord.TextChannel:
    extra = perms.text_flags(toggles)
    existing = guild.get_channel(channel_id) if channel_id else None
    if isinstance(existing, discord.TextChannel):
        if existing.name != name:
            await existing.edit(name=name, reason=_REASON)
        await perms.sync_role_overwrite(
            existing, role, overwrites.member_grant(extra), _REASON
        )
        return existing
    return await guild.create_text_channel(
        name,
        category=category,
        overwrites=overwrites.team_channel(guild, role, staff, extra),
        reason=_REASON,
    )


async def ensure_voice_channel(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    channel_id: int | None,
    name: str,
    role: discord.Role,
    staff: discord.Role | None,
    toggles: dict[str, bool] | None = None,
) -> discord.VoiceChannel:
    extra = perms.voice_flags(toggles)
    existing = guild.get_channel(channel_id) if channel_id else None
    if isinstance(existing, discord.VoiceChannel):
        if existing.name != name:
            await existing.edit(name=name, reason=_REASON)
        await perms.sync_role_overwrite(
            existing, role, overwrites.member_grant(extra), _REASON
        )
        return existing
    return await guild.create_voice_channel(
        name,
        category=category,
        overwrites=overwrites.team_channel(guild, role, staff, extra),
        reason=_REASON,
    )


async def reconcile_members(
    guild: discord.Guild, role: discord.Role, wanted_ids: set[int]
) -> None:
    """Make the role's holders exactly *wanted_ids*, adding and removing.

    A roster edit on the website has to be able to take access away, not only
    grant it, or a removed member keeps reading their old team's channel.
    """
    current = {m.id for m in role.members}
    for user_id in wanted_ids - current:
        member = guild.get_member(user_id)
        if member is None:
            logger.debug("tilerace: user {} not in guild, skipping role", user_id)
            continue
        with contextlib.suppress(discord.HTTPException):
            await member.add_roles(role, reason=_REASON)
    for user_id in current - wanted_ids:
        member = guild.get_member(user_id)
        if member is None:
            continue
        with contextlib.suppress(discord.HTTPException):
            await member.remove_roles(role, reason=_REASON)


async def delete_channel(guild: discord.Guild, channel_id: int | None) -> None:
    channel = guild.get_channel(channel_id) if channel_id else None
    if channel is not None:
        with contextlib.suppress(discord.HTTPException):
            await channel.delete(reason=_REASON)


async def delete_role(guild: discord.Guild, role_id: int | None) -> None:
    role = guild.get_role(role_id) if role_id else None
    if role is not None:
        with contextlib.suppress(discord.HTTPException):
            await role.delete(reason=_REASON)


def team_names(team: dict[str, object]) -> tuple[str, str, str]:
    """Role, text-channel and voice-channel names for one team payload."""
    name = str(team.get("name") or "")
    slug = str(team.get("slug") or "")
    return (
        naming.role_name(name),
        naming.channel_name(name, slug),
        naming.voice_name(name),
    )

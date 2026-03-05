from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def _fmt_age(max_age: int) -> str:
    """Format invite max_age seconds into a human-readable string."""
    if max_age >= 86400:
        return f"{max_age // 86400}d"
    if max_age >= 3600:
        return f"{max_age // 3600}h"
    return f"{max_age // 60}m"


def register(registrar: EventRegistrar) -> None:
    """Register invite event handlers."""
    service = registrar.service

    async def on_invite_create(invite: discord.Invite) -> None:
        if not invite.guild or invite.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Invite Created",
            color=CATEGORY_COLORS[LogCategory.INVITES],
            timestamp=datetime.now(UTC),
        )
        if invite.inviter:
            embed.set_author(
                name=str(invite.inviter),
                icon_url=invite.inviter.display_avatar.url,
            )
            embed.add_field(
                name="Created By", value=invite.inviter.mention, inline=True
            )
        if invite.channel:
            embed.add_field(name="Channel", value=invite.channel.mention, inline=True)
        embed.add_field(name="Code", value=f"`{invite.code}`", inline=True)
        embed.add_field(
            name="Max Uses",
            value=str(invite.max_uses) if invite.max_uses else "∞",
            inline=True,
        )
        embed.add_field(
            name="Expires",
            value=_fmt_age(invite.max_age) if invite.max_age else "Never",
            inline=True,
        )
        if invite.temporary:
            embed.add_field(
                name="Temporary", value="Yes — kicked when disconnected", inline=False
            )
        logger.debug(f"ActionLog[invites]: invite {invite.code} created")
        await service.post(LogCategory.INVITES, embed)

    async def on_invite_delete(invite: discord.Invite) -> None:
        if not invite.guild or invite.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Invite Deleted",
            color=discord.Color.dark_gray(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Code", value=f"`{invite.code}`", inline=True)
        if invite.channel:
            embed.add_field(name="Channel", value=invite.channel.mention, inline=True)
        if invite.inviter:
            embed.add_field(
                name="Created By", value=invite.inviter.mention, inline=True
            )
        logger.debug(f"ActionLog[invites]: invite {invite.code} deleted")
        await service.post(LogCategory.INVITES, embed)

    registrar.add("on_invite_create", on_invite_create)
    registrar.add("on_invite_delete", on_invite_delete)

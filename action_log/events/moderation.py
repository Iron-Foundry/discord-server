from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register moderation event handlers."""
    service = registrar.service

    async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
        if guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Member Banned",
            color=CATEGORY_COLORS[LogCategory.MODERATION],
            timestamp=datetime.now(UTC),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention} (`{user}`)", inline=True)
        embed.set_footer(text=f"User ID: {user.id}")
        logger.debug(f"ActionLog[moderation]: {user} was banned")
        await service.post(LogCategory.MODERATION, embed)

    async def on_member_unban(guild: discord.Guild, user: discord.User) -> None:
        if guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Member Unbanned",
            color=discord.Color.green(),
            timestamp=datetime.now(UTC),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention} (`{user}`)", inline=True)
        embed.set_footer(text=f"User ID: {user.id}")
        logger.debug(f"ActionLog[moderation]: {user} was unbanned")
        await service.post(LogCategory.MODERATION, embed)

    registrar.add("on_member_ban", on_member_ban)
    registrar.add("on_member_unban", on_member_unban)

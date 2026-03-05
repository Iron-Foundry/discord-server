from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register member event handlers."""
    service = registrar.service

    async def on_member_join(member: discord.Member) -> None:
        if member.guild.id != service.guild.id:
            return

        created = discord.utils.format_dt(member.created_at, style="R")
        embed = discord.Embed(
            title="Member Joined",
            color=CATEGORY_COLORS[LogCategory.MEMBERS],
            timestamp=datetime.now(UTC),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Account Created", value=created, inline=True)
        embed.add_field(
            name="Member Count",
            value=str(member.guild.member_count),
            inline=True,
        )
        embed.set_footer(text=f"User ID: {member.id}")
        logger.debug(f"ActionLog[members]: {member} joined")
        await service.post(LogCategory.MEMBERS, embed)

    async def on_member_remove(member: discord.Member) -> None:
        if member.guild.id != service.guild.id:
            return

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        roles_value = " ".join(roles) if roles else "*none*"
        if len(roles_value) > 1024:
            roles_value = f"{len(roles)} roles"

        embed = discord.Embed(
            title="Member Left",
            color=discord.Color.dark_gray(),
            timestamp=datetime.now(UTC),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(
            name="User", value=f"{member.mention} (`{member}`)", inline=False
        )
        embed.add_field(name="Roles", value=roles_value, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        logger.debug(f"ActionLog[members]: {member} left")
        await service.post(LogCategory.MEMBERS, embed)

    async def on_member_update(before: discord.Member, after: discord.Member) -> None:
        if before.guild.id != service.guild.id:
            return

        # Nickname change
        if before.nick != after.nick:
            embed = discord.Embed(
                title="Nickname Changed",
                color=CATEGORY_COLORS[LogCategory.MEMBERS],
                timestamp=datetime.now(UTC),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="User", value=after.mention, inline=False)
            embed.add_field(name="Before", value=before.nick or "*none*", inline=True)
            embed.add_field(name="After", value=after.nick or "*none*", inline=True)
            embed.set_footer(text=f"User ID: {after.id}")
            logger.debug(
                f"ActionLog[members]: {after} nick '{before.nick}' → '{after.nick}'"
            )
            await service.post(LogCategory.MEMBERS, embed)

        # Role changes
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = discord.Embed(
                title="Member Roles Updated",
                color=CATEGORY_COLORS[LogCategory.MEMBERS],
                timestamp=datetime.now(UTC),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="User", value=after.mention, inline=False)
            if added:
                embed.add_field(
                    name="Added",
                    value=" ".join(r.mention for r in added),
                    inline=True,
                )
            if removed:
                embed.add_field(
                    name="Removed",
                    value=" ".join(r.mention for r in removed),
                    inline=True,
                )
            embed.set_footer(text=f"User ID: {after.id}")
            logger.debug(
                f"ActionLog[members]: {after} roles "
                f"+{[r.name for r in added]} -{[r.name for r in removed]}"
            )
            await service.post(LogCategory.MEMBERS, embed)

    registrar.add("on_member_join", on_member_join)
    registrar.add("on_member_remove", on_member_remove)
    registrar.add("on_member_update", on_member_update)

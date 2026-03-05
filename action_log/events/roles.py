from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register role event handlers."""
    service = registrar.service

    async def on_guild_role_create(role: discord.Role) -> None:
        if role.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Role Created",
            color=CATEGORY_COLORS[LogCategory.ROLES],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=role.mention, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(
            name="Hoisted", value="Yes" if role.hoist else "No", inline=True
        )
        embed.add_field(
            name="Mentionable",
            value="Yes" if role.mentionable else "No",
            inline=True,
        )
        embed.set_footer(text=f"Role ID: {role.id}")
        logger.debug(f"ActionLog[roles]: role '{role.name}' created")
        await service.post(LogCategory.ROLES, embed)

    async def on_guild_role_delete(role: discord.Role) -> None:
        if role.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Role Deleted",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=role.name, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.set_footer(text=f"Role ID: {role.id}")
        logger.debug(f"ActionLog[roles]: role '{role.name}' deleted")
        await service.post(LogCategory.ROLES, embed)

    async def on_guild_role_update(before: discord.Role, after: discord.Role) -> None:
        if before.guild.id != service.guild.id:
            return

        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** {before.name} → {after.name}")
        if before.color != after.color:
            lines.append(f"**Color:** {before.color} → {after.color}")
        if before.hoist != after.hoist:
            state = "hoisted" if after.hoist else "unhoisted"
            lines.append(f"**Display:** now {state}")
        if before.mentionable != after.mentionable:
            state = "mentionable" if after.mentionable else "not mentionable"
            lines.append(f"**Mention:** now {state}")
        if before.permissions != after.permissions:
            lines.append("**Permissions:** updated")

        if not lines:
            return

        embed = discord.Embed(
            title="Role Updated",
            description="\n".join(lines),
            color=CATEGORY_COLORS[LogCategory.ROLES],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Role", value=after.mention, inline=True)
        embed.set_footer(text=f"Role ID: {after.id}")
        logger.debug(f"ActionLog[roles]: role '{after.name}' updated — {lines}")
        await service.post(LogCategory.ROLES, embed)

    registrar.add("on_guild_role_create", on_guild_role_create)
    registrar.add("on_guild_role_delete", on_guild_role_delete)
    registrar.add("on_guild_role_update", on_guild_role_update)

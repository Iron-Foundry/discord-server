from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register thread event handlers."""
    service = registrar.service

    async def on_thread_create(thread: discord.Thread) -> None:
        if thread.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Thread Created",
            color=CATEGORY_COLORS[LogCategory.CHANNELS],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=thread.mention, inline=True)
        embed.add_field(
            name="Parent",
            value=thread.parent.mention if thread.parent else "*unknown*",
            inline=True,
        )
        if thread.owner:
            embed.add_field(name="Created By", value=thread.owner.mention, inline=True)
        embed.set_footer(text=f"Thread ID: {thread.id}")
        logger.debug(f"ActionLog[channels]: thread '{thread.name}' created")
        await service.post(LogCategory.CHANNELS, embed)

    async def on_thread_update(before: discord.Thread, after: discord.Thread) -> None:
        if before.guild.id != service.guild.id:
            return

        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** {before.name} → {after.name}")
        if before.archived != after.archived:
            lines.append(f"**Archived:** {'yes' if after.archived else 'no'}")
        if before.locked != after.locked:
            lines.append(f"**Locked:** {'yes' if after.locked else 'no'}")
        if before.slowmode_delay != after.slowmode_delay:
            lines.append(
                f"**Slowmode:** {before.slowmode_delay}s → {after.slowmode_delay}s"
            )

        if not lines:
            return

        embed = discord.Embed(
            title="Thread Updated",
            description="\n".join(lines),
            color=CATEGORY_COLORS[LogCategory.CHANNELS],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Thread", value=after.mention, inline=True)
        if after.parent:
            embed.add_field(name="Parent", value=after.parent.mention, inline=True)
        embed.set_footer(text=f"Thread ID: {after.id}")
        logger.debug(f"ActionLog[channels]: thread '{after.name}' updated — {lines}")
        await service.post(LogCategory.CHANNELS, embed)

    async def on_thread_delete(thread: discord.Thread) -> None:
        if thread.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Thread Deleted",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=f"#{thread.name}", inline=True)
        embed.add_field(
            name="Parent",
            value=thread.parent.mention if thread.parent else "*unknown*",
            inline=True,
        )
        embed.set_footer(text=f"Thread ID: {thread.id}")
        logger.debug(f"ActionLog[channels]: thread '{thread.name}' deleted")
        await service.post(LogCategory.CHANNELS, embed)

    registrar.add("on_thread_create", on_thread_create)
    registrar.add("on_thread_update", on_thread_update)
    registrar.add("on_thread_delete", on_thread_delete)

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register message event handlers."""
    service = registrar.service

    async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return  # embed load — no real content change

        channel = before.channel
        parent_id = channel.parent_id if isinstance(channel, discord.Thread) else None
        if service.is_ignored(channel.id, parent_id=parent_id):
            return

        embed = discord.Embed(
            title="Message Edited",
            color=CATEGORY_COLORS[LogCategory.MESSAGES],
            timestamp=datetime.now(UTC),
        )
        embed.set_author(
            name=str(before.author),
            icon_url=before.author.display_avatar.url,
        )
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(
            name="Before",
            value=before.content[:1024] or "*empty*",
            inline=False,
        )
        embed.add_field(
            name="After",
            value=after.content[:1024] or "*empty*",
            inline=False,
        )
        embed.add_field(
            name="Jump",
            value=f"[Go to message]({after.jump_url})",
            inline=False,
        )
        embed.set_footer(text=f"Message ID: {before.id}")
        logger.debug(f"ActionLog[messages]: edited by {before.author} in #{channel}")
        await service.post(LogCategory.MESSAGES, embed)

    async def on_message_delete(message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        channel = message.channel
        parent_id = channel.parent_id if isinstance(channel, discord.Thread) else None
        if service.is_ignored(channel.id, parent_id=parent_id):
            return

        embed = discord.Embed(
            title="Message Deleted",
            color=CATEGORY_COLORS[LogCategory.MESSAGES],
            timestamp=datetime.now(UTC),
        )
        embed.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url,
        )
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        if message.content:
            embed.add_field(
                name="Content",
                value=message.content[:1024],
                inline=False,
            )
        if message.attachments:
            embed.add_field(
                name="Attachments",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        embed.set_footer(text=f"Message ID: {message.id}")
        logger.debug(f"ActionLog[messages]: message {message.id} deleted in #{channel}")
        await service.post(LogCategory.MESSAGES, embed)

    async def on_bulk_message_delete(
        messages: list[discord.Message],
    ) -> None:
        if not messages or not messages[0].guild:
            return

        channel = messages[0].channel
        parent_id = channel.parent_id if isinstance(channel, discord.Thread) else None
        if service.is_ignored(channel.id, parent_id=parent_id):
            return

        embed = discord.Embed(
            title="Bulk Message Delete",
            description=f"{len(messages)} messages were deleted.",
            color=CATEGORY_COLORS[LogCategory.MESSAGES],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Count", value=str(len(messages)), inline=True)
        logger.debug(
            f"ActionLog[messages]: {len(messages)} messages bulk-deleted in #{channel}"
        )
        await service.post(LogCategory.MESSAGES, embed)

    registrar.add("on_message_edit", on_message_edit)
    registrar.add("on_message_delete", on_message_delete)
    registrar.add("on_bulk_message_delete", on_bulk_message_delete)

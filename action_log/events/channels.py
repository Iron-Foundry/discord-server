from __future__ import annotations

import discord.abc
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def _channel_type(channel: discord.abc.GuildChannel) -> str:
    if isinstance(channel, discord.TextChannel):
        return "Text Channel"
    if isinstance(channel, discord.VoiceChannel):
        return "Voice Channel"
    if isinstance(channel, discord.CategoryChannel):
        return "Category"
    if isinstance(channel, discord.StageChannel):
        return "Stage Channel"
    if isinstance(channel, discord.ForumChannel):
        return "Forum Channel"
    return "Channel"


def register(registrar: EventRegistrar) -> None:
    """Register channel event handlers."""
    service = registrar.service

    async def on_guild_channel_create(
        channel: discord.abc.GuildChannel,
    ) -> None:
        if channel.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Channel Created",
            color=CATEGORY_COLORS[LogCategory.CHANNELS],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=channel.mention, inline=True)
        embed.add_field(name="Type", value=_channel_type(channel), inline=True)
        if channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)
        embed.set_footer(text=f"Channel ID: {channel.id}")
        logger.debug(f"ActionLog[channels]: channel #{channel.name} created")
        await service.post(LogCategory.CHANNELS, embed)

    async def on_guild_channel_delete(
        channel: discord.abc.GuildChannel,
    ) -> None:
        if channel.guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Channel Deleted",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=f"#{channel.name}", inline=True)
        embed.add_field(name="Type", value=_channel_type(channel), inline=True)
        if channel.category:
            embed.add_field(name="Category", value=channel.category.name, inline=True)
        embed.set_footer(text=f"Channel ID: {channel.id}")
        logger.debug(f"ActionLog[channels]: channel #{channel.name} deleted")
        await service.post(LogCategory.CHANNELS, embed)

    async def on_guild_channel_update(
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        if before.guild.id != service.guild.id:
            return

        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** #{before.name} → #{after.name}")
        if before.category != after.category:
            bc = before.category.name if before.category else "none"
            ac = after.category.name if after.category else "none"
            lines.append(f"**Category:** {bc} → {ac}")

        if isinstance(before, discord.TextChannel) and isinstance(
            after, discord.TextChannel
        ):
            if before.topic != after.topic:
                lines.append(
                    f"**Topic Before:** {before.topic or '*none*'}\n"
                    f"**Topic After:** {after.topic or '*none*'}"
                )
            if before.slowmode_delay != after.slowmode_delay:
                lines.append(
                    f"**Slowmode:** {before.slowmode_delay}s → {after.slowmode_delay}s"
                )
            if before.nsfw != after.nsfw:
                state = "enabled" if after.nsfw else "disabled"
                lines.append(f"**NSFW:** {state}")

        if not lines:
            return

        embed = discord.Embed(
            title="Channel Updated",
            description="\n".join(lines),
            color=CATEGORY_COLORS[LogCategory.CHANNELS],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Channel", value=after.mention, inline=True)
        embed.set_footer(text=f"Channel ID: {after.id}")
        logger.debug(f"ActionLog[channels]: #{after.name} updated — {lines}")
        await service.post(LogCategory.CHANNELS, embed)

    async def on_stage_instance_create(stage: discord.StageInstance) -> None:
        if stage.guild_id != service.guild.id:
            return

        embed = discord.Embed(
            title="Stage Started",
            color=CATEGORY_COLORS[LogCategory.CHANNELS],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Topic", value=stage.topic, inline=False)
        embed.add_field(name="Channel", value=f"<#{stage.channel_id}>", inline=True)
        embed.add_field(
            name="Privacy",
            value=str(stage.privacy_level).replace("StagePrivacyLevel.", "").title(),
            inline=True,
        )
        embed.set_footer(text=f"Stage ID: {stage.id}")
        logger.debug(f"ActionLog[channels]: stage started — '{stage.topic}'")
        await service.post(LogCategory.CHANNELS, embed)

    async def on_stage_instance_update(
        before: discord.StageInstance, after: discord.StageInstance
    ) -> None:
        if after.guild_id != service.guild.id:
            return

        lines: list[str] = []
        if before.topic != after.topic:
            lines.append(f"**Topic:** {before.topic} → {after.topic}")
        if before.privacy_level != after.privacy_level:
            lines.append(
                f"**Privacy:** "
                f"{str(before.privacy_level).replace('StagePrivacyLevel.', '').title()} → "
                f"{str(after.privacy_level).replace('StagePrivacyLevel.', '').title()}"
            )

        if not lines:
            return

        embed = discord.Embed(
            title="Stage Updated",
            description="\n".join(lines),
            color=CATEGORY_COLORS[LogCategory.CHANNELS],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Channel", value=f"<#{after.channel_id}>", inline=True)
        embed.set_footer(text=f"Stage ID: {after.id}")
        logger.debug(f"ActionLog[channels]: stage updated — '{after.topic}'")
        await service.post(LogCategory.CHANNELS, embed)

    async def on_stage_instance_delete(stage: discord.StageInstance) -> None:
        if stage.guild_id != service.guild.id:
            return

        embed = discord.Embed(
            title="Stage Ended",
            color=discord.Color.dark_gray(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Topic", value=stage.topic, inline=False)
        embed.add_field(name="Channel", value=f"<#{stage.channel_id}>", inline=True)
        embed.set_footer(text=f"Stage ID: {stage.id}")
        logger.debug(f"ActionLog[channels]: stage ended — '{stage.topic}'")
        await service.post(LogCategory.CHANNELS, embed)

    registrar.add("on_guild_channel_create", on_guild_channel_create)
    registrar.add("on_guild_channel_delete", on_guild_channel_delete)
    registrar.add("on_guild_channel_update", on_guild_channel_update)
    registrar.add("on_stage_instance_create", on_stage_instance_create)
    registrar.add("on_stage_instance_update", on_stage_instance_update)
    registrar.add("on_stage_instance_delete", on_stage_instance_delete)

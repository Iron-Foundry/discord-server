from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register voice state event handlers."""
    service = registrar.service

    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.guild.id != service.guild.id:
            return

        # Channel join / leave / move
        if before.channel != after.channel:
            if before.channel is None:
                embed = discord.Embed(
                    title="Joined Voice Channel",
                    color=CATEGORY_COLORS[LogCategory.VOICE],
                    timestamp=datetime.now(UTC),
                )
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                embed.add_field(name="User", value=member.mention, inline=True)
                assert after.channel is not None
                embed.add_field(
                    name="Channel", value=after.channel.mention, inline=True
                )
                embed.set_footer(text=f"User ID: {member.id}")
                logger.debug(f"ActionLog[voice]: {member} joined #{after.channel}")
                await service.post(LogCategory.VOICE, embed)

            elif after.channel is None:
                embed = discord.Embed(
                    title="Left Voice Channel",
                    color=discord.Color.dark_gray(),
                    timestamp=datetime.now(UTC),
                )
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                embed.add_field(name="User", value=member.mention, inline=True)
                embed.add_field(
                    name="Channel", value=f"#{before.channel.name}", inline=True
                )
                embed.set_footer(text=f"User ID: {member.id}")
                logger.debug(f"ActionLog[voice]: {member} left #{before.channel}")
                await service.post(LogCategory.VOICE, embed)

            else:
                embed = discord.Embed(
                    title="Moved Voice Channel",
                    color=CATEGORY_COLORS[LogCategory.VOICE],
                    timestamp=datetime.now(UTC),
                )
                embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                embed.add_field(name="User", value=member.mention, inline=True)
                embed.add_field(
                    name="From", value=f"#{before.channel.name}", inline=True
                )
                embed.add_field(name="To", value=after.channel.mention, inline=True)
                embed.set_footer(text=f"User ID: {member.id}")
                logger.debug(
                    f"ActionLog[voice]: {member} moved "
                    f"#{before.channel} → #{after.channel}"
                )
                await service.post(LogCategory.VOICE, embed)

            return

        # State changes while in a channel
        if after.channel is None:
            return

        lines: list[str] = []
        if before.self_mute != after.self_mute:
            lines.append(
                f"**Self-mute:** {'enabled' if after.self_mute else 'disabled'}"
            )
        if before.self_deaf != after.self_deaf:
            lines.append(
                f"**Self-deafen:** {'enabled' if after.self_deaf else 'disabled'}"
            )
        if before.mute != after.mute:
            lines.append(f"**Server mute:** {'enabled' if after.mute else 'disabled'}")
        if before.deaf != after.deaf:
            lines.append(
                f"**Server deafen:** {'enabled' if after.deaf else 'disabled'}"
            )
        if before.self_stream != after.self_stream:
            lines.append(f"**Stream:** {'started' if after.self_stream else 'ended'}")
        if before.self_video != after.self_video:
            lines.append(f"**Camera:** {'on' if after.self_video else 'off'}")

        if not lines:
            return

        embed = discord.Embed(
            title="Voice State Updated",
            description="\n".join(lines),
            color=CATEGORY_COLORS[LogCategory.VOICE],
            timestamp=datetime.now(UTC),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Channel", value=after.channel.mention, inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        logger.debug(f"ActionLog[voice]: {member} state updated in #{after.channel}")
        await service.post(LogCategory.VOICE, embed)

    registrar.add("on_voice_state_update", on_voice_state_update)

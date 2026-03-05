from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register guild-level event handlers."""
    service = registrar.service

    async def on_guild_update(before: discord.Guild, after: discord.Guild) -> None:
        if before.id != service.guild.id:
            return

        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** {before.name} → {after.name}")
        if before.icon != after.icon:
            lines.append("**Icon:** updated")
        if before.description != after.description:
            lines.append(
                f"**Description:** "
                f"{before.description or '*none*'} → "
                f"{after.description or '*none*'}"
            )
        if before.verification_level != after.verification_level:
            lines.append(
                f"**Verification Level:** "
                f"{before.verification_level} → {after.verification_level}"
            )
        if before.explicit_content_filter != after.explicit_content_filter:
            lines.append(
                f"**Content Filter:** "
                f"{before.explicit_content_filter} → "
                f"{after.explicit_content_filter}"
            )

        if not lines:
            return

        embed = discord.Embed(
            title="Guild Updated",
            description="\n".join(lines),
            color=CATEGORY_COLORS[LogCategory.GUILD],
            timestamp=datetime.now(UTC),
        )
        embed.set_footer(text=f"Guild ID: {after.id}")
        if after.icon:
            embed.set_thumbnail(url=after.icon.url)
        logger.debug(f"ActionLog[guild]: '{after.name}' updated — {lines}")
        await service.post(LogCategory.GUILD, embed)

    async def on_guild_emojis_update(
        guild: discord.Guild,
        before: list[discord.Emoji],
        after: list[discord.Emoji],
    ) -> None:
        if guild.id != service.guild.id:
            return

        before_ids = {e.id for e in before}
        after_ids = {e.id for e in after}
        added = [e for e in after if e.id not in before_ids]
        removed = [e for e in before if e.id not in after_ids]

        if not added and not removed:
            return

        embed = discord.Embed(
            title="Emojis Updated",
            color=CATEGORY_COLORS[LogCategory.GUILD],
            timestamp=datetime.now(UTC),
        )
        if added:
            embed.add_field(
                name=f"Added ({len(added)})",
                value=" ".join(str(e) for e in added),
                inline=False,
            )
        if removed:
            embed.add_field(
                name=f"Removed ({len(removed)})",
                value=" ".join(f"`:{e.name}:`" for e in removed),
                inline=False,
            )
        embed.set_footer(text=f"Guild ID: {guild.id}")
        logger.debug(
            f"ActionLog[guild]: emojis +{[e.name for e in added]} "
            f"-{[e.name for e in removed]}"
        )
        await service.post(LogCategory.GUILD, embed)

    async def on_guild_stickers_update(
        guild: discord.Guild,
        before: list[discord.GuildSticker],
        after: list[discord.GuildSticker],
    ) -> None:
        if guild.id != service.guild.id:
            return

        before_ids = {s.id for s in before}
        after_ids = {s.id for s in after}
        added = [s for s in after if s.id not in before_ids]
        removed = [s for s in before if s.id not in after_ids]

        if not added and not removed:
            return

        embed = discord.Embed(
            title="Stickers Updated",
            color=CATEGORY_COLORS[LogCategory.GUILD],
            timestamp=datetime.now(UTC),
        )
        if added:
            embed.add_field(
                name=f"Added ({len(added)})",
                value="\n".join(f"`{s.name}`" for s in added),
                inline=False,
            )
        if removed:
            embed.add_field(
                name=f"Removed ({len(removed)})",
                value="\n".join(f"`{s.name}`" for s in removed),
                inline=False,
            )
        embed.set_footer(text=f"Guild ID: {guild.id}")
        logger.debug(
            f"ActionLog[guild]: stickers +{[s.name for s in added]} "
            f"-{[s.name for s in removed]}"
        )
        await service.post(LogCategory.GUILD, embed)

    registrar.add("on_guild_update", on_guild_update)
    registrar.add("on_guild_emojis_update", on_guild_emojis_update)
    registrar.add("on_guild_stickers_update", on_guild_stickers_update)

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

    registrar.add("on_guild_update", on_guild_update)

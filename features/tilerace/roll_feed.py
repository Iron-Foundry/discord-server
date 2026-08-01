"""Posts the roll card api-backend publishes into the team's own channel."""

from __future__ import annotations

from typing import Any

import discord
from loguru import logger

from .roll_layout import roll_layout


async def announce(guild: discord.Guild, command: dict[str, Any]) -> bool:
    """Render one roll into the channel api-backend named.

    Nothing is reported back: the bot creates no objects here, so a failed post
    costs a message and never a roll that is already recorded.
    """
    channel = guild.get_channel(int(command.get("channel_id") or 0))
    if not isinstance(channel, discord.TextChannel):
        logger.warning(
            "TileRaceService: roll feedback has no channel {} in this guild",
            command.get("channel_id"),
        )
        return False
    try:
        await channel.send(view=roll_layout(command))
    except discord.HTTPException as exc:
        logger.warning("TileRaceService: could not post roll feedback - {}", exc)
        return False
    return True

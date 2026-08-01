"""The persistent Submit panel that lives in the event's submissions channel."""

from __future__ import annotations

from typing import Any

import discord
from loguru import logger

from . import flow
from .layout import panel_container

PANEL_CUSTOM_ID = "tilerace_submit"


class SubmitButton(discord.ui.Button[Any]):
    def __init__(self) -> None:
        super().__init__(
            label="Submit",
            style=discord.ButtonStyle.primary,
            custom_id=PANEL_CUSTOM_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await flow.open_submission(interaction)


class SubmissionPanel(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(panel_container(SubmitButton()))


async def refresh(channel: discord.TextChannel) -> discord.Message | None:
    """Make sure the channel's newest message is a live Submit panel.

    Re-posting is cheap and idempotent enough: an old panel from a previous
    event is deleted rather than left behind for someone to press.
    """
    try:
        async for message in channel.history(limit=20):
            if message.author == channel.guild.me and message.components:
                await message.delete()
        return await channel.send(view=SubmissionPanel())
    except discord.HTTPException as exc:
        logger.warning("tilerace submissions: could not refresh the panel - {}", exc)
        return None

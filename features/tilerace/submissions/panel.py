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


async def ensure(channel: discord.TextChannel) -> discord.Message | None:
    """Make sure the channel holds exactly one live Submit panel.

    Runs on every setup and sync, so a channel added to an event that was
    already provisioned still gets its button. An existing panel is left in
    place: re-posting on each roster edit would bury the channel and move the
    message teams have scrolled back to.
    """
    try:
        async for message in channel.history(limit=50):
            if message.author == channel.guild.me and message.components:
                return message
        return await channel.send(view=SubmissionPanel())
    except discord.HTTPException as exc:
        logger.warning("tilerace submissions: could not post the panel - {}", exc)
        return None

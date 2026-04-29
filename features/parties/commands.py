"""Party slash commands - staff-only panel setup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from core.command_infra.checks import is_staff

if TYPE_CHECKING:
    from features.parties.service import PartyService


class PartyGroup(app_commands.Group, name="party", description="Party panel management"):
    """Staff commands for managing the party panel."""

    def __init__(self, service: PartyService) -> None:
        super().__init__()
        self._service = service

    @app_commands.command(
        name="setup",
        description="Post (or re-post) the party panel in a channel.",
    )
    @app_commands.describe(channel="Channel to post the party panel in")
    @is_staff()
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        """Post the party panel in the specified channel."""
        await interaction.response.defer(ephemeral=True)
        try:
            await self._service.setup_panel(channel)
        except Exception as exc:
            logger.exception(
                "PartyCommands: setup_panel failed for {} in #{}: {}",
                interaction.user,
                channel.name,
                exc,
            )
            await interaction.followup.send(
                f"Failed to post panel: `{exc}`", ephemeral=True
            )
            return
        await interaction.followup.send(
            f"Party panel posted in {channel.mention}.", ephemeral=True
        )
        logger.info(
            "PartyCommands: {} set up panel in #{}",
            interaction.user,
            channel.name,
        )

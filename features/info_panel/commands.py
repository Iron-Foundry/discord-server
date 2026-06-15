"""Info panel slash commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from core.command_infra.checks import handle_check_failure, is_staff

if TYPE_CHECKING:
    from features.info_panel.service import InfoPanelService


class InfoPanelGroup(app_commands.Group, name="infopanel", description="Info panel management"):
    def __init__(self, service: InfoPanelService) -> None:
        super().__init__()
        self._service = service

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await handle_check_failure(interaction, error)

    @app_commands.command(name="post", description="Post the info panel in a channel.")
    @app_commands.describe(channel="Channel to post the info panel in")
    @is_staff()
    async def post(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if self._service._messages:
            await interaction.followup.send(
                "Panel is already posted. Use `/infopanel clear` first.", ephemeral=True
            )
            return
        try:
            await self._service.post_panel(channel)
        except Exception as exc:
            logger.exception("InfoPanel: post failed in #{}: {}", channel.name, exc)
            await interaction.followup.send(f"Failed to post panel: `{exc}`", ephemeral=True)
            return
        await interaction.followup.send(
            f"Info panel posted in {channel.mention}.", ephemeral=True
        )
        logger.info("InfoPanel: {} posted panel in #{}", interaction.user, channel.name)

    @app_commands.command(name="refresh", description="Refresh the info panel with latest data.")
    @is_staff()
    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not self._service._messages:
            await interaction.followup.send(
                "No panel posted. Use `/infopanel post #channel` first.", ephemeral=True
            )
            return
        try:
            await self._service.refresh_panel()
        except Exception as exc:
            logger.exception("InfoPanel: refresh failed: {}", exc)
            await interaction.followup.send(f"Refresh failed: `{exc}`", ephemeral=True)
            return
        await interaction.followup.send("Info panel refreshed.", ephemeral=True)
        logger.info("InfoPanel: {} triggered refresh", interaction.user)

    @app_commands.command(name="clear", description="Delete the info panel messages.")
    @is_staff()
    async def clear(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not self._service._messages:
            await interaction.followup.send("No panel to clear.", ephemeral=True)
            return
        try:
            await self._service.clear_panel()
        except Exception as exc:
            logger.exception("InfoPanel: clear failed: {}", exc)
            await interaction.followup.send(f"Clear failed: `{exc}`", ephemeral=True)
            return
        await interaction.followup.send("Info panel cleared.", ephemeral=True)
        logger.info("InfoPanel: {} cleared panel", interaction.user)

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from core.command_infra.checks import handle_check_failure

if TYPE_CHECKING:
    from features.user_keys.service import UserKeyService

# OSRS RSN: 1–12 chars, letters / digits / spaces / hyphens
_RSN_RE = re.compile(r"^[A-Za-z0-9 \-]{1,12}$")


class AccountGroup(
    app_commands.Group,
    name="account",
    description="View or manage your Foundry account",
):
    """Slash commands for a member's linked account."""

    def __init__(self, service: UserKeyService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /account status
    # ------------------------------------------------------------------

    @app_commands.command(
        name="status",
        description="Show your linked account details",
    )
    async def status(self, interaction: discord.Interaction) -> None:
        """Display the member's current account status."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.", ephemeral=True
            )
            return

        logger.debug(f"account status: invoked by {interaction.user}")

        profile = await self._service.get_user_profile(interaction.user)
        key = await self._service.get_key(interaction.user)

        rsn = profile.get("rsn") if profile else None
        opt_out = profile.get("stats_opt_out", False) if profile else False

        embed = discord.Embed(
            title="Your Foundry Account",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="RSN",
            value=rsn if rsn else "*Not linked - use `/account link`*",
            inline=False,
        )
        embed.add_field(
            name="RuneLite API Key",
            value="✓ Active" if key else "*None - use `/userkey new`*",
            inline=True,
        )
        embed.add_field(
            name="Stats Collection",
            value="Opted out" if opt_out else "Active",
            inline=True,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /account link <rsn>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="link",
        description="Link your Old School RuneScape username to your Discord account",
    )
    @app_commands.describe(rsn="Your in-game username (1–12 characters)")
    async def link(self, interaction: discord.Interaction, rsn: str) -> None:
        """Link an RSN to the member's account."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.", ephemeral=True
            )
            return

        rsn = rsn.strip()
        if not _RSN_RE.match(rsn):
            await interaction.response.send_message(
                "Invalid RSN. Must be 1–12 characters (letters, numbers, spaces, hyphens).",
                ephemeral=True,
            )
            return

        logger.debug(f"account link: {interaction.user} → {rsn!r}")
        await self._service.link_rsn(interaction.user, rsn)
        await interaction.response.send_message(
            f"RSN **{rsn}** linked to your account.",
            ephemeral=True,
        )

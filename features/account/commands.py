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


def _validate_rsn(rsn: str) -> str | None:
    """Return error message if invalid, None if valid."""
    rsn = rsn.strip()
    if not rsn or not _RSN_RE.match(rsn):
        return "Invalid RSN. Must be 1–12 characters (letters, numbers, spaces, hyphens)."
    return None


class AltsGroup(app_commands.Group, name="alts", description="Manage linked alt accounts"):
    """Subcommands for managing multiple linked RSNs."""

    def __init__(self, service: UserKeyService) -> None:
        super().__init__()
        self._service = service

    @app_commands.command(name="list", description="Show all your linked RSNs")
    async def list_alts(self, interaction: discord.Interaction) -> None:
        """Display all accounts linked to the member."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.", ephemeral=True
            )
            return

        accounts = await self._service.get_user_accounts(interaction.user)
        if not accounts:
            await interaction.response.send_message(
                "No RSNs linked. Use `/account link` to add one.", ephemeral=True
            )
            return

        lines = []
        for acc in accounts:
            marker = " (primary)" if acc["is_primary"] else ""
            lines.append(f"**{acc['rsn']}**{marker}")

        await interaction.response.send_message(
            "**Your linked RSNs:**\n" + "\n".join(lines), ephemeral=True
        )

    @app_commands.command(name="add", description="Link an additional RSN to your account")
    @app_commands.describe(rsn="Alt RSN to link (1–12 characters)")
    async def add(self, interaction: discord.Interaction, rsn: str) -> None:
        """Add an alt RSN."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.", ephemeral=True
            )
            return

        err = _validate_rsn(rsn)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return

        rsn = rsn.strip()
        logger.debug("account alts add: {} → {!r}", interaction.user, rsn)
        error = await self._service.add_account(interaction.user, rsn)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.send_message(
            f"RSN **{rsn}** added to your account.", ephemeral=True
        )

    @app_commands.command(
        name="set-primary", description="Change your primary RSN"
    )
    @app_commands.describe(rsn="RSN to make your primary account")
    async def set_primary(self, interaction: discord.Interaction, rsn: str) -> None:
        """Promote an RSN to primary."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.", ephemeral=True
            )
            return

        rsn = rsn.strip()
        logger.debug("account alts set-primary: {} → {!r}", interaction.user, rsn)
        error = await self._service.set_primary_account(interaction.user, rsn)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.send_message(
            f"**{rsn}** is now your primary RSN.", ephemeral=True
        )

    @app_commands.command(name="remove", description="Remove a linked alt RSN")
    @app_commands.describe(rsn="Alt RSN to remove")
    async def remove(self, interaction: discord.Interaction, rsn: str) -> None:
        """Remove an alt RSN."""
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.", ephemeral=True
            )
            return

        rsn = rsn.strip()
        logger.debug("account alts remove: {} → {!r}", interaction.user, rsn)
        error = await self._service.remove_account(interaction.user, rsn)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.send_message(
            f"RSN **{rsn}** removed from your account.", ephemeral=True
        )


class AccountGroup(
    app_commands.Group,
    name="account",
    description="View or manage your Foundry account",
):
    """Slash commands for a member's linked account."""

    def __init__(self, service: UserKeyService) -> None:
        super().__init__()
        self._service = service
        self.add_command(AltsGroup(service))

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
        accounts = await self._service.get_user_accounts(interaction.user)
        key = await self._service.get_key(interaction.user)

        rsn = profile.get("rsn") if profile else None
        opt_out = profile.get("stats_opt_out", False) if profile else False

        # Build RSN field value
        if accounts:
            rsn_lines = []
            for acc in accounts:
                marker = " **(primary)**" if acc["is_primary"] else ""
                rsn_lines.append(f"{acc['rsn']}{marker}")
            rsn_value = "\n".join(rsn_lines)
        else:
            rsn_value = rsn if rsn else "*Not linked - use `/account link`*"

        embed = discord.Embed(
            title="Your Foundry Account",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="RSN", value=rsn_value, inline=False)
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

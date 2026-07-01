from __future__ import annotations

import discord
from discord import app_commands
from loguru import logger

from features.admin.link_service import LinkResult, auto_link_members
from features.admin.refresh_service import RefreshResult, refresh_all_roles
from features.admin.service import AdminService

_OWNER_ID = 225683257146998785
_MAX_LIST = 20


def _build_refresh_embed(result: RefreshResult, dry_run: bool) -> discord.Embed:
    title = "Role refresh preview" if dry_run else "Role refresh complete"
    color = discord.Color.blurple() if dry_run else discord.Color.green()
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Updated", value=str(result.updated), inline=True)
    embed.add_field(
        name="Not in guild", value=str(result.skipped_not_in_guild), inline=True
    )
    embed.add_field(name="Errors", value=str(result.errors), inline=True)
    return embed


def _build_embed(result: LinkResult, dry_run: bool) -> discord.Embed:
    title = "Auto-link preview" if dry_run else "Auto-link complete"
    color = discord.Color.blurple() if dry_run else discord.Color.green()
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Linked", value=str(len(result.linked)), inline=True)
    embed.add_field(name="Skipped", value=str(len(result.skipped)), inline=True)
    embed.add_field(name="Errors", value=str(len(result.errors)), inline=True)

    if result.linked:
        sample = result.linked[:_MAX_LIST]
        suffix = (
            f"\n...and {len(result.linked) - _MAX_LIST} more"
            if len(result.linked) > _MAX_LIST
            else ""
        )
        embed.add_field(
            name="Linked pairs",
            value="\n".join(sample) + suffix,
            inline=False,
        )

    if result.errors:
        embed.add_field(
            name="Errors (first 5)",
            value="\n".join(result.errors[:5]),
            inline=False,
        )

    return embed


class AdminGroup(app_commands.Group, name="admin", description="Admin-only utilities"):
    def __init__(self, service: AdminService) -> None:
        super().__init__()
        self._service = service

    @app_commands.command(
        name="link-members",
        description="Auto-link Discord members to WOM RSNs by display name",
    )
    @app_commands.describe(dry_run="Preview matches without writing anything")
    async def link_members(
        self, interaction: discord.Interaction, dry_run: bool = False
    ) -> None:
        if interaction.user.id != _OWNER_ID:
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        logger.info(
            "admin/link-members: started by {} (dry_run={})", interaction.user, dry_run
        )

        result = await auto_link_members(
            self._service.guild,
            self._service.session_factory,
            dry_run,
        )

        embed = _build_embed(result, dry_run)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="refresh-roles",
        description="Pull current Discord roles and clan rank for all linked users",
    )
    @app_commands.describe(dry_run="Preview what would change without writing anything")
    async def refresh_roles(
        self, interaction: discord.Interaction, dry_run: bool = False
    ) -> None:
        if interaction.user.id != _OWNER_ID:
            await interaction.response.send_message("Not authorised.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        logger.info(
            "admin/refresh-roles: started by {} (dry_run={})", interaction.user, dry_run
        )

        result = await refresh_all_roles(
            self._service.guild,
            self._service.session_factory,
            dry_run,
        )

        embed = _build_refresh_embed(result, dry_run)
        await interaction.followup.send(embed=embed, ephemeral=True)

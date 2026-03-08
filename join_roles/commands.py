from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from command_infra.checks import handle_check_failure, is_senior_staff, is_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry

if TYPE_CHECKING:
    from join_roles.service import JoinRoleService


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the joinrole command group."""
    registry.add_group(
        HelpGroup(
            name="joinrole",
            description="Manage roles automatically assigned to new members",
            commands=[
                HelpEntry(
                    "/joinrole add <role>",
                    "Add a role to the join roles list",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/joinrole remove <role>",
                    "Remove a role from the join roles list",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/joinrole list",
                    "List all configured join roles",
                    "Staff",
                ),
            ],
        )
    )


class JoinRoleGroup(
    app_commands.Group, name="joinrole", description="Manage join roles"
):
    """Slash command group for managing automatically assigned join roles."""

    def __init__(self, service: JoinRoleService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /joinrole add <role>
    # ------------------------------------------------------------------

    @app_commands.command(name="add", description="Add a role to the join roles list")
    @app_commands.describe(role="The role to assign to new members")
    @is_senior_staff()
    async def add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        logger.debug(f"JoinRole: add invoked by {interaction.user}, role={role.name!r}")
        added = await self._service.add_role(role.id)
        if added:
            await interaction.response.send_message(
                f"✅ {role.mention} will now be assigned to new members.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"{role.mention} is already in the join roles list.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /joinrole remove <role>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="remove", description="Remove a role from the join roles list"
    )
    @app_commands.describe(role="The role to remove")
    @is_senior_staff()
    async def remove(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        logger.debug(
            f"JoinRole: remove invoked by {interaction.user}, role={role.name!r}"
        )
        removed = await self._service.remove_role(role.id)
        if removed:
            await interaction.response.send_message(
                f"⛔ {role.mention} removed from join roles.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{role.mention} was not in the join roles list.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /joinrole list
    # ------------------------------------------------------------------

    @app_commands.command(name="list", description="List all configured join roles")
    @is_staff()
    async def list_roles(self, interaction: discord.Interaction) -> None:
        logger.debug(f"JoinRole: list invoked by {interaction.user}")
        role_ids = self._service.role_ids
        embed = discord.Embed(title="Join Roles", color=discord.Color.blurple())
        if not role_ids:
            embed.description = "No join roles configured."
        else:
            embed.description = "\n".join(f"<@&{rid}>" for rid in role_ids)
        await interaction.response.send_message(embed=embed, ephemeral=True)

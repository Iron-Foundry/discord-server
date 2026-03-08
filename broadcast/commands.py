from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from command_infra.checks import handle_check_failure, is_senior_staff, is_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry

if TYPE_CHECKING:
    from broadcast.service import BroadcastService


def make_broadcast_context_menu(
    service: BroadcastService,
) -> app_commands.ContextMenu:
    """Return a ready-to-add 'Forward to Members' message context menu."""

    @app_commands.context_menu(name="Forward to Members")
    @is_staff()
    async def forward_to_members(
        interaction: discord.Interaction, message: discord.Message
    ) -> None:
        if service.role is None:
            await interaction.response.send_message(
                "No broadcast role configured. Use `/broadcast setrole` first.",
                ephemeral=True,
            )
            return

        logger.debug(
            f"Broadcast: forward_to_members invoked by {interaction.user}"
            f" for message {message.id}"
        )
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await service.broadcast_message(message)

        not_reached = result.failed + result.skipped
        await interaction.followup.send(
            f"Forwarded to **{result.sent}** members"
            + (f" ({not_reached} could not be reached)." if not_reached else "."),
            ephemeral=True,
        )

    return forward_to_members  # type: ignore[return-value]


class BroadcastGroup(
    app_commands.Group, name="broadcast", description="Manage broadcast settings"
):
    """Slash commands for configuring the broadcast role."""

    def __init__(self, service: BroadcastService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /broadcast setrole <role>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setrole",
        description="Set the role whose members receive forwarded messages",
    )
    @app_commands.describe(
        role="Members of this role will receive DMs when a message is forwarded"
    )
    @is_senior_staff()
    async def setrole(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        logger.debug(
            f"Broadcast: setrole invoked by {interaction.user}, role={role.name!r}"
        )
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.set_role(role.id)
        member_count = sum(1 for m in role.members if not m.bot)
        await interaction.followup.send(
            f"Broadcast role set to {role.mention} — **{member_count}** eligible members.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /broadcast status
    # ------------------------------------------------------------------

    @app_commands.command(
        name="status", description="Show the current broadcast configuration"
    )
    @is_staff()
    async def status(self, interaction: discord.Interaction) -> None:
        role = self._service.role
        if role is None:
            await interaction.response.send_message(
                "No broadcast role configured. Use `/broadcast setrole` to set one.",
                ephemeral=True,
            )
            return
        member_count = sum(1 for m in role.members if not m.bot)
        await interaction.response.send_message(
            f"Broadcast role: {role.mention} — **{member_count}** eligible members.",
            ephemeral=True,
        )


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the broadcast command group."""
    registry.add_group(
        HelpGroup(
            name="broadcast",
            description="Forward messages to role members via DM",
            commands=[
                HelpEntry(
                    "/broadcast status",
                    "Show the current broadcast role and eligible member count",
                    "Staff",
                ),
                HelpEntry(
                    "/broadcast setrole <role>",
                    "Set the role whose members receive forwarded messages",
                    "Senior Staff",
                ),
                HelpEntry(
                    "Right-click message → Forward to Members",
                    "DM the message to all members with the broadcast role",
                    "Staff",
                ),
            ],
        )
    )

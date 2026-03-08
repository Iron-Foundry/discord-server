from __future__ import annotations

import discord
from discord import app_commands
from typing import TYPE_CHECKING

from command_infra.checks import handle_check_failure, is_senior_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService

_PROTECTED = {"mongodb"}


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the handler command group."""
    registry.add_group(
        HelpGroup(
            name="handler",
            description="Manage ticket transcript handlers",
            commands=[
                HelpEntry(
                    "/handler list",
                    "List all transcript handlers and their status",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/handler enable <name>",
                    "Enable a transcript handler",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/handler disable <name>",
                    "Disable a transcript handler",
                    "Senior Staff",
                ),
            ],
        )
    )


class HandlerGroup(
    app_commands.Group, name="handler", description="Manage transcript handlers"
):
    def __init__(self, service: TicketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /handler list
    # ------------------------------------------------------------------

    @app_commands.command(
        name="list", description="List all transcript handlers and their status"
    )
    @is_senior_staff()
    async def list_handlers(self, interaction: discord.Interaction) -> None:
        handlers = self._service.list_handlers()
        embed = discord.Embed(
            title="Transcript Handlers", color=discord.Color.blurple()
        )
        for name, enabled in handlers:
            status = "✅ Enabled" if enabled else "⛔ Disabled"
            protected = " 🔒" if name in _PROTECTED else ""
            embed.add_field(name=f"`{name}`{protected}", value=status, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /handler enable <name>
    # ------------------------------------------------------------------

    @app_commands.command(name="enable", description="Enable a transcript handler")
    @app_commands.describe(name="The handler to enable")
    @is_senior_staff()
    async def enable(self, interaction: discord.Interaction, name: str) -> None:
        if self._service.enable_handler(name):
            await interaction.response.send_message(
                f"✅ Handler `{name}` enabled.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Unknown handler `{name}`.", ephemeral=True
            )

    @enable.autocomplete("name")
    async def enable_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=n, value=n)
            for n, enabled in self._service.list_handlers()
            if not enabled and current.lower() in n.lower()
        ]

    # ------------------------------------------------------------------
    # /handler disable <name>
    # ------------------------------------------------------------------

    @app_commands.command(name="disable", description="Disable a transcript handler")
    @app_commands.describe(name="The handler to disable")
    @is_senior_staff()
    async def disable(self, interaction: discord.Interaction, name: str) -> None:
        if name in _PROTECTED:
            await interaction.response.send_message(
                f"Handler `{name}` cannot be disabled.", ephemeral=True
            )
            return
        if self._service.disable_handler(name):
            await interaction.response.send_message(
                f"⛔ Handler `{name}` disabled.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Unknown handler `{name}`.", ephemeral=True
            )

    @disable.autocomplete("name")
    async def disable_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=n, value=n)
            for n, enabled in self._service.list_handlers()
            if enabled and n not in _PROTECTED and current.lower() in n.lower()
        ]

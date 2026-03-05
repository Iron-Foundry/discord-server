from __future__ import annotations

import discord
from discord import app_commands
from typing import TYPE_CHECKING

from commands.checks import handle_check_failure, is_senior_staff, is_staff
from commands.help_registry import HelpEntry, HelpGroup, HelpRegistry
from tickets.views.ticket_tools import CloseReasonModal

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the ticket and tickettype command groups."""
    registry.add_group(
        HelpGroup(
            name="ticket",
            description="Open, close, and manage support tickets",
            commands=[
                HelpEntry("/ticket open <type>", "Open a new ticket", "Everyone"),
                HelpEntry("/ticket close", "Close the current ticket", "Everyone"),
                HelpEntry(
                    "/ticket reopen <ticket_id>", "Reopen a closed ticket", "Everyone"
                ),
                HelpEntry("/ticket tools", "Spawn the moderator tools panel", "Staff"),
                HelpEntry("/ticket add <user>", "Add a user to this ticket", "Staff"),
                HelpEntry(
                    "/ticket remove <user>",
                    "Remove a user from this ticket",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket freeze",
                    "Freeze the 24-hour inactivity timeout",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket unfreeze",
                    "Unfreeze the 24-hour inactivity timeout",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket list <user>",
                    "List a user's recent tickets",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket panel <channel>",
                    "Post the ticket panel to a channel",
                    "Senior Staff",
                ),
            ],
        )
    )
    registry.add_group(
        HelpGroup(
            name="tickettype",
            description="Manage which ticket types are available",
            commands=[
                HelpEntry(
                    "/tickettype list",
                    "List all ticket types and their status",
                    "Everyone",
                ),
                HelpEntry(
                    "/tickettype enable <type>",
                    "Enable a ticket type",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/tickettype disable <type>",
                    "Disable a ticket type",
                    "Senior Staff",
                ),
            ],
        )
    )


class TicketGroup(
    app_commands.Group, name="ticket", description="Ticket management commands"
):
    def __init__(self, service: TicketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /ticket panel <channel>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="panel", description="Post the ticket panel to a channel"
    )
    @app_commands.describe(channel="The channel to post the panel in")
    @is_senior_staff()
    async def panel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.post_panel(channel)
        await interaction.followup.send(
            f"Panel posted to {channel.mention}.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /ticket open <type>
    # ------------------------------------------------------------------

    @app_commands.command(name="open", description="Open a ticket")
    @app_commands.describe(ticket_type="The type of ticket to open")
    async def open(self, interaction: discord.Interaction, ticket_type: str) -> None:
        t = self._service.type_registry.get(ticket_type)
        if not t or not t.enabled:
            await interaction.response.send_message(
                "That ticket type is not available.", ephemeral=True
            )
            return

        modal = t.build_creation_modal(
            callback=lambda intr, meta: self._service.create_ticket(
                intr, ticket_type, meta
            )
        )
        if modal is not None:
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            ticket = await self._service.create_ticket(interaction, ticket_type, {})
            if ticket:
                await interaction.followup.send(
                    f"Ticket created: {ticket.channel.mention}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Failed to create ticket.", ephemeral=True
                )

    @open.autocomplete("ticket_type")
    async def open_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=t.display_name, value=t.identifier)
            for t in self._service.type_registry.get_enabled()
            if current.lower() in t.display_name.lower()
        ]

    # ------------------------------------------------------------------
    # /ticket close
    # ------------------------------------------------------------------

    @app_commands.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            CloseReasonModal(self._service, ticket.ticket_id)
        )

    # ------------------------------------------------------------------
    # /ticket tools
    # ------------------------------------------------------------------

    @app_commands.command(name="tools", description="Spawn the moderator tools panel")
    @is_staff()
    async def tools(self, interaction: discord.Interaction) -> None:
        await self._service.spawn_tools(interaction)

    # ------------------------------------------------------------------
    # /ticket add <user>
    # ------------------------------------------------------------------

    @app_commands.command(name="add", description="Add a user to this ticket")
    @app_commands.describe(user="The member to add")
    @is_staff()
    async def add(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        success = await self._service.add_user(ticket.ticket_id, user)
        if success:
            await interaction.response.send_message(
                f"Added {user.mention} to the ticket."
            )
        else:
            await interaction.response.send_message(
                "Failed to add user.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /ticket remove <user>
    # ------------------------------------------------------------------

    @app_commands.command(name="remove", description="Remove a user from this ticket")
    @app_commands.describe(user="The member to remove")
    @is_staff()
    async def remove(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        success = await self._service.remove_user(ticket.ticket_id, user)
        if success:
            await interaction.response.send_message(
                f"Removed {user.mention} from the ticket."
            )
        else:
            await interaction.response.send_message(
                "Failed to remove user.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /ticket freeze / unfreeze
    # ------------------------------------------------------------------

    @app_commands.command(
        name="freeze", description="Freeze the 24-hour inactivity timeout"
    )
    @is_staff()
    async def freeze(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        await self._service.freeze_timeout(ticket.ticket_id)
        await interaction.response.send_message(
            "⏸️ Timeout frozen — this ticket won't auto-close."
        )

    @app_commands.command(
        name="unfreeze", description="Unfreeze the 24-hour inactivity timeout"
    )
    @is_staff()
    async def unfreeze(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        await self._service.unfreeze_timeout(ticket.ticket_id)
        await interaction.response.send_message(
            "▶️ Timeout unfrozen — 24-hour timer resumed."
        )

    # ------------------------------------------------------------------
    # /ticket reopen
    # ------------------------------------------------------------------

    @app_commands.command(name="reopen", description="Reopen a closed ticket")
    @app_commands.describe(ticket_id="The ticket ID to reopen")
    async def reopen(self, interaction: discord.Interaction, ticket_id: int) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.reopen_ticket(
            ticket_id=ticket_id,
            reopener=interaction.user,
        )
        if success:
            await interaction.followup.send(
                f"Ticket #{ticket_id:04d} has been reopened.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Could not reopen ticket #{ticket_id:04d}. It may not exist or may not be closed.",
                ephemeral=True,
            )

    @reopen.autocomplete("ticket_id")
    async def reopen_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        tickets = await self._service.get_closed_tickets_by_user(
            interaction.user.id, limit=25
        )
        return [
            app_commands.Choice(
                name=f"#{t.ticket_id:04d} — {t.ticket_type.replace('_', ' ').title()}",
                value=t.ticket_id,
            )
            for t in tickets
            if not current or current in str(t.ticket_id)
        ]

    # ------------------------------------------------------------------
    # /ticket list <user>
    # ------------------------------------------------------------------

    @app_commands.command(name="list", description="List a user's recent tickets")
    @app_commands.describe(user="The member to look up")
    @is_staff()
    async def list_tickets(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        tickets = await self._service.get_recent_tickets_by_user(user.id, limit=10)

        embed = discord.Embed(
            title=f"Tickets — {user.display_name}",
            color=discord.Color.blurple(),
        )

        if not tickets:
            embed.description = "No tickets found for this user."
        else:
            for t in tickets:
                type_name = t.ticket_type.replace("_", " ").title()
                created = discord.utils.format_dt(t.created_at, style="d")
                embed.add_field(
                    name=f"#{t.ticket_id:04d} — {type_name}",
                    value=f"Status: **{t.status.value.capitalize()}** | Opened: {created}",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)


class TicketTypeGroup(
    app_commands.Group, name="tickettype", description="Manage ticket types"
):
    def __init__(self, service: TicketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /tickettype enable <type>
    # ------------------------------------------------------------------

    @app_commands.command(name="enable", description="Enable a ticket type")
    @app_commands.describe(ticket_type="The ticket type to enable")
    @is_senior_staff()
    async def enable(self, interaction: discord.Interaction, ticket_type: str) -> None:
        t = self._service.type_registry.get(ticket_type)
        if not t:
            await interaction.response.send_message(
                "Unknown ticket type.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.enable_type(ticket_type)
        await interaction.followup.send(
            f"✅ **{t.display_name}** is now enabled.", ephemeral=True
        )

    @enable.autocomplete("ticket_type")
    async def enable_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=t.display_name, value=t.identifier)
            for t in self._service.type_registry.get_all()
            if not t.enabled and current.lower() in t.display_name.lower()
        ]

    # ------------------------------------------------------------------
    # /tickettype disable <type>
    # ------------------------------------------------------------------

    @app_commands.command(name="disable", description="Disable a ticket type")
    @app_commands.describe(ticket_type="The ticket type to disable")
    @is_senior_staff()
    async def disable(self, interaction: discord.Interaction, ticket_type: str) -> None:
        t = self._service.type_registry.get(ticket_type)
        if not t:
            await interaction.response.send_message(
                "Unknown ticket type.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.disable_type(ticket_type)
        await interaction.followup.send(
            f"⛔ **{t.display_name}** is now disabled.", ephemeral=True
        )

    @disable.autocomplete("ticket_type")
    async def disable_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=t.display_name, value=t.identifier)
            for t in self._service.type_registry.get_all()
            if t.enabled and current.lower() in t.display_name.lower()
        ]

    # ------------------------------------------------------------------
    # /tickettype list
    # ------------------------------------------------------------------

    @app_commands.command(
        name="list", description="List all ticket types and their status"
    )
    async def list_types(self, interaction: discord.Interaction) -> None:
        types = self._service.type_registry.get_all()
        if not types:
            await interaction.response.send_message(
                "No ticket types registered.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎫 Ticket Types",
            color=discord.Color.blurple(),
        )
        for t in types:
            status = "✅ Enabled" if t.enabled else "⛔ Disabled"
            embed.add_field(
                name=f"{t.emoji} {t.display_name}",
                value=f"`{t.identifier}` — {status}\n{t.description}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

"""Change-type button and select for the ticket sticky bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from features.tickets.views._layout_helpers import status_layout

if TYPE_CHECKING:
    from features.tickets.models.ticket import TicketTypeConfig
    from features.tickets.ticket_service import TicketService


class ChangeTypeSelect(discord.ui.Select):
    def __init__(
        self, service: TicketService, ticket_id: int, types: list[TicketTypeConfig]
    ) -> None:
        self._service = service
        self._ticket_id = ticket_id
        options = [
            discord.SelectOption(
                label=t.display_name, value=t.identifier, description=t.description
            )
            for t in types
        ]
        super().__init__(
            placeholder="Select new type...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                view=status_layout("Server only."), ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_id(self._ticket_id)
        if not ticket or not any(
            team.is_member(interaction.user) for team in ticket.ticket_type.teams
        ):
            await interaction.response.send_message(
                view=status_layout("Staff only."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.change_ticket_type(
            self._ticket_id, self.values[0], interaction.user
        )
        msg = "Ticket type updated." if success else "Could not change ticket type."
        await interaction.followup.send(view=status_layout(msg), ephemeral=True)


class _ChangeTypeSelectView(discord.ui.View):
    def __init__(
        self, service: TicketService, ticket_id: int, types: list[TicketTypeConfig]
    ) -> None:
        super().__init__(timeout=60)
        self.add_item(ChangeTypeSelect(service, ticket_id, types))


class ChangeTypeButton(discord.ui.Button):
    """Opens an ephemeral type picker. Used in the sticky bar."""

    def __init__(self, service: TicketService) -> None:
        super().__init__(
            label="Change Type",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_sticky_change_type",
        )
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "No active ticket in this channel.", ephemeral=True
            )
            return
        if not isinstance(interaction.user, discord.Member) or not any(
            team.is_member(interaction.user) for team in ticket.ticket_type.teams
        ):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        current_type = ticket.record.ticket_type
        enabled_types = [
            t
            for t in self._service.type_registry.get_all()
            if t.enabled and t.identifier != current_type
        ]
        if not enabled_types:
            await interaction.followup.send(
                view=status_layout("No other ticket types available."), ephemeral=True
            )
            return
        view = _ChangeTypeSelectView(self._service, ticket.ticket_id, enabled_types)
        await interaction.followup.send(
            "Select the new ticket type:", view=view, ephemeral=True
        )

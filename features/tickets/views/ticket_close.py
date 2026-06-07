"""Close button and reason modal for the ticket sticky bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Ticket Reason",
        placeholder="This will be DM'd to the ticket creator...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    staff_note = discord.ui.TextInput(
        label="Staff Note (Internal)",
        placeholder="Archived for future reference - not shown to the user.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, service: TicketService, ticket_id: int) -> None:
        super().__init__()
        self._service = service
        self._ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.close_ticket(
            ticket_id=self._ticket_id,
            closer=interaction.user,
            reason=self.reason.value,
            note=self.staff_note.value or None,
        )
        if not success:
            await interaction.followup.send(
                "Failed to close the ticket.", ephemeral=True
            )


class CloseButton(discord.ui.Button):
    """Shows CloseReasonModal. Used in the sticky bar."""

    def __init__(self, service: TicketService) -> None:
        super().__init__(
            label="Close",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id="ticket_sticky_close",
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
                "No active ticket found in this channel.", ephemeral=True
            )
            return
        if not isinstance(interaction.user, discord.Member) or not any(
            team.is_member(interaction.user) for team in ticket.ticket_type.teams
        ):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return
        await interaction.response.send_modal(
            CloseReasonModal(self._service, ticket.ticket_id)
        )

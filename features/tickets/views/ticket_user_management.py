"""Add/Remove user buttons for the ticket sticky toolbar."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


class _AddUserSelect(discord.ui.UserSelect):
    def __init__(self, service: TicketService, channel_id: int) -> None:
        super().__init__(placeholder="Select a user to add...", min_values=1, max_values=1)
        self._service = service
        self._channel_id = channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        user = self.values[0]
        if not isinstance(user, discord.Member):
            await interaction.response.send_message(
                "Must be used in a server.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(self._channel_id)
        if not ticket:
            await interaction.response.send_message(
                "No active ticket found.", ephemeral=True
            )
            return
        success = await self._service.add_user(ticket.ticket_id, user)
        if success:
            await interaction.response.send_message(
                f"Added {user.mention} to the ticket.", ephemeral=True
            )
        else:
            await interaction.response.send_message("Failed to add user.", ephemeral=True)


class _RemoveUserSelect(discord.ui.UserSelect):
    def __init__(self, service: TicketService, channel_id: int) -> None:
        super().__init__(
            placeholder="Select a user to remove...", min_values=1, max_values=1
        )
        self._service = service
        self._channel_id = channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        user = self.values[0]
        if not isinstance(user, discord.Member):
            await interaction.response.send_message(
                "Must be used in a server.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(self._channel_id)
        if not ticket:
            await interaction.response.send_message(
                "No active ticket found.", ephemeral=True
            )
            return
        success = await self._service.remove_user(ticket.ticket_id, user)
        if success:
            await interaction.response.send_message(
                f"Removed {user.mention} from the ticket.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Failed to remove user.", ephemeral=True
            )


class AddUserButton(discord.ui.Button):
    def __init__(self, service: TicketService) -> None:
        super().__init__(
            label="Add User",
            style=discord.ButtonStyle.success,
            emoji="➕",
            custom_id="ticket_sticky_add_user",
        )
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket or not isinstance(interaction.user, discord.Member) or not any(
            team.is_member(interaction.user) for team in ticket.ticket_type.teams
        ):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return
        view = discord.ui.View(timeout=60)
        view.add_item(_AddUserSelect(self._service, interaction.channel_id))
        await interaction.response.send_message(
            "Select a user to add to this ticket:", view=view, ephemeral=True
        )


class RemoveUserButton(discord.ui.Button):
    def __init__(self, service: TicketService) -> None:
        super().__init__(
            label="Remove User",
            style=discord.ButtonStyle.primary,
            emoji="➖",
            custom_id="ticket_sticky_remove_user",
        )
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket or not isinstance(interaction.user, discord.Member) or not any(
            team.is_member(interaction.user) for team in ticket.ticket_type.teams
        ):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return
        view = discord.ui.View(timeout=60)
        view.add_item(_RemoveUserSelect(self._service, interaction.channel_id))
        await interaction.response.send_message(
            "Select a user to remove from this ticket:", view=view, ephemeral=True
        )

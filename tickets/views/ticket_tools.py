from __future__ import annotations

import discord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService
    from tickets.models.ticket import Ticket


class CloseReasonModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Ticket Reason",
        placeholder="This will be DM'd to the ticket creator...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    staff_note = discord.ui.TextInput(
        label="Staff Note (Internal)",
        placeholder="Archived for future reference — not shown to the user.",
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


class AddUserModal(discord.ui.Modal, title="Add User to Ticket"):
    user_input = discord.ui.TextInput(
        label="User ID",
        placeholder="Paste the user's Discord ID",
        max_length=20,
    )

    def __init__(self, service: TicketService, ticket_id: int) -> None:
        super().__init__()
        self._service = service
        self._ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return
        try:
            user_id = int(self.user_input.value.strip().lstrip("<@!").rstrip(">"))
            member = interaction.guild.get_member(user_id)
            if not member:
                await interaction.response.send_message(
                    "User not found in this server.", ephemeral=True
                )
                return
            success = await self._service.add_user(self._ticket_id, member)
            msg = (
                f"Added {member.mention} to the ticket."
                if success
                else "Failed to add user."
            )
            await interaction.response.send_message(msg, ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid user ID.", ephemeral=True)


class RemoveUserModal(discord.ui.Modal, title="Remove User from Ticket"):
    user_input = discord.ui.TextInput(
        label="User ID",
        placeholder="Paste the user's Discord ID",
        max_length=20,
    )

    def __init__(self, service: TicketService, ticket_id: int) -> None:
        super().__init__()
        self._service = service
        self._ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return
        try:
            user_id = int(self.user_input.value.strip().lstrip("<@!").rstrip(">"))
            member = interaction.guild.get_member(user_id)
            if not member:
                await interaction.response.send_message(
                    "User not found in this server.", ephemeral=True
                )
                return
            success = await self._service.remove_user(self._ticket_id, member)
            msg = (
                f"Removed {member.mention} from the ticket."
                if success
                else "Failed to remove user."
            )
            await interaction.response.send_message(msg, ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid user ID.", ephemeral=True)


class TicketToolsView(discord.ui.View):
    """Moderator tools panel that can be spawned inside any open ticket channel."""

    def __init__(self, service: TicketService, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id

    async def _get_ticket(self, interaction: discord.Interaction) -> Ticket | None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return None
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "Could not find an active ticket in this channel.", ephemeral=True
            )
        return ticket

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        row=0,
    )
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        ticket = await self._get_ticket(interaction)
        if not ticket:
            return
        await interaction.response.send_modal(
            CloseReasonModal(self._service, ticket.ticket_id)
        )

    @discord.ui.button(
        label="Freeze Timeout",
        style=discord.ButtonStyle.secondary,
        emoji="❄️",
        row=0,
    )
    async def freeze_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        ticket = await self._get_ticket(interaction)
        if not ticket:
            return
        if ticket.is_frozen:
            await self._service.unfreeze_timeout(ticket.ticket_id)
            button.label = "Freeze Timeout"
            button.emoji = "❄️"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "Timeout unfrozen — 24h timer resumed.", ephemeral=True
            )
        else:
            await self._service.freeze_timeout(ticket.ticket_id)
            button.label = "Unfreeze Timeout"
            button.emoji = "🔥"
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                "Timeout frozen — ticket won't auto-close.", ephemeral=True
            )

    @discord.ui.button(
        label="Add User",
        style=discord.ButtonStyle.secondary,
        emoji="➕",
        row=1,
    )
    async def add_user_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        ticket = await self._get_ticket(interaction)
        if not ticket:
            return
        await interaction.response.send_modal(
            AddUserModal(self._service, ticket.ticket_id)
        )

    @discord.ui.button(
        label="Remove User",
        style=discord.ButtonStyle.secondary,
        emoji="➖",
        row=1,
    )
    async def remove_user_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        ticket = await self._get_ticket(interaction)
        if not ticket:
            return
        await interaction.response.send_modal(
            RemoveUserModal(self._service, ticket.ticket_id)
        )


def build_tools_embed() -> discord.Embed:
    return discord.Embed(
        title="🛠️ Ticket Tools",
        description="Staff tools for managing this ticket.",
        color=discord.Color.orange(),
    )

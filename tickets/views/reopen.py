from __future__ import annotations

import discord
from datetime import datetime, UTC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService


class ReopenView(discord.ui.View):
    """
    Posted in the ticket channel after closure.
    Any user with channel access (or staff) can click Reopen.
    """

    def __init__(self, service: TicketService, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id

    @discord.ui.button(
        label="Reopen Ticket",
        style=discord.ButtonStyle.success,
        emoji="🔓",
    )
    async def reopen_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.reopen_ticket(
            ticket_id=self._ticket_id,
            reopener=interaction.user,
        )
        if success:
            button.disabled = True
            if interaction.message:
                await interaction.message.edit(view=self)
            await interaction.followup.send("Ticket reopened.", ephemeral=True)
        else:
            await interaction.followup.send(
                "Failed to reopen the ticket.", ephemeral=True
            )


def build_closed_embed(
    ticket_id: int, closer: discord.Member, reason: str | None
) -> discord.Embed:
    embed = discord.Embed(
        title="🔒 Ticket Closed",
        description=(
            f"This ticket was closed by {closer.mention}.\n\n"
            + (f"**Reason:** {reason}" if reason else "")
        ),
        color=discord.Color.red(),
        timestamp=datetime.now(UTC),
    )
    embed.set_footer(text="Click the button below to reopen this ticket.")
    return embed

"""Closed ticket layout with reopen button - Discord Components V2."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from features.tickets.views._layout_helpers import status_layout

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


class _ReopenButton(discord.ui.Button):
    def __init__(self, service: TicketService, ticket_id: int) -> None:
        super().__init__(
            label="Reopen Ticket",
            style=discord.ButtonStyle.success,
            emoji="🔓",
            custom_id=f"ticket_reopen_{ticket_id}",
        )
        self._service = service
        self._ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if isinstance(interaction.user, discord.Member):
            reopener = interaction.user
        else:
            reopener = self._service.guild.get_member(interaction.user.id)
            if reopener is None:
                try:
                    reopener = await self._service.guild.fetch_member(interaction.user.id)
                except discord.HTTPException:
                    reopener = None
            if reopener is None:
                await interaction.response.send_message(
                    view=status_layout("You must be a member of the server to reopen tickets."),
                    ephemeral=True,
                )
                return
        await interaction.response.defer(ephemeral=True, thinking=True)
        new_channel = await self._service.reopen_ticket(
            ticket_id=self._ticket_id,
            reopener=reopener,
        )
        if new_channel:
            if interaction.message:
                # Disable reopen button after use
                disabled_view = build_reopen_layout(
                    self._service,
                    self._ticket_id,
                    reopener,
                    None,
                    disabled=True,
                )
                await interaction.message.edit(view=disabled_view)
            await interaction.followup.send(
                view=status_layout(f"Ticket reopened: {new_channel.mention}"),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                view=status_layout("Failed to reopen the ticket."), ephemeral=True
            )


def build_reopen_layout(
    service: TicketService,
    ticket_id: int,
    closer: discord.Member,
    reason: str | None,
    *,
    disabled: bool = False,
) -> ReopenLayout:
    return ReopenLayout(
        service=service,
        ticket_id=ticket_id,
        closer=closer,
        reason=reason,
        disabled=disabled,
    )


class ReopenLayout(discord.ui.LayoutView):
    """Posted in DM after ticket closes. Persistent."""

    def __init__(
        self,
        *,
        service: TicketService,
        ticket_id: int,
        closer: discord.Member,
        reason: str | None,
        disabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        lines = [
            f"## 🔒 Ticket #{ticket_id:04d} Closed",
            f"Closed by {closer.mention}.",
        ]
        if reason:
            lines.append(f"**Reason:** {reason}")

        btn = _ReopenButton(service, ticket_id)
        btn.disabled = disabled

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(content="\n".join(lines)),
                discord.ui.Separator(),
                discord.ui.ActionRow(btn),
                accent_colour=discord.Color.red(),
            )
        )

"""Sticky staff tools bar - auto-posted on ticket create, re-posted after 20s idle."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from features.tickets.views.ticket_close import CloseButton
from features.tickets.views.ticket_type_change import ChangeTypeButton
from features.tickets.views.ticket_user_management import AddUserButton, RemoveUserButton

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


class _FreezeButton(discord.ui.Button):
    def __init__(self, service: TicketService, is_frozen: bool = False) -> None:
        self._service = service
        label = "Unfreeze" if is_frozen else "Freeze"
        emoji = "🔥" if is_frozen else "❄️"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            emoji=emoji,
            custom_id="ticket_sticky_freeze",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "No active ticket found.", ephemeral=True
            )
            return
        if not isinstance(interaction.user, discord.Member) or not any(
            team.is_member(interaction.user) for team in ticket.ticket_type.teams
        ):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return
        if ticket.is_frozen:
            await self._service.unfreeze_timeout(ticket.ticket_id)
            new_view = build_sticky_view(
                self._service, ticket.record.ticket_type, is_frozen=False
            )
            await interaction.response.edit_message(view=new_view)
            await interaction.followup.send(
                "Timeout unfrozen - 24h timer resumed.", ephemeral=True
            )
        else:
            await self._service.freeze_timeout(ticket.ticket_id)
            new_view = build_sticky_view(
                self._service, ticket.record.ticket_type, is_frozen=True
            )
            await interaction.response.edit_message(view=new_view)
            await interaction.followup.send(
                "Timeout frozen - ticket won't auto-close.", ephemeral=True
            )


def build_sticky_view(
    service: TicketService, ticket_type_id: str = "", *, is_frozen: bool = False
) -> TicketStickyView:
    return TicketStickyView(service=service, is_frozen=is_frozen)


class TicketStickyView(discord.ui.LayoutView):
    """Minimal persistent staff bar. Auto-posted on create, re-posted after 20s idle."""

    def __init__(
        self,
        *,
        service: TicketService,
        is_frozen: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(content="### Ticket Toolbar"),
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    CloseButton(service),
                    _FreezeButton(service, is_frozen),
                    ChangeTypeButton(service),
                    AddUserButton(service),
                    RemoveUserButton(service),
                ),
                accent_colour=discord.Color.blurple(),
            )
        )

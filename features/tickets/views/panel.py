"""Persistent ticket panel - Discord Components V2."""

from __future__ import annotations

from datetime import datetime, UTC
from typing import TYPE_CHECKING

import discord

from features.tickets.views._layout_helpers import header_items, status_layout

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


class _TicketOpenButton(discord.ui.Button):
    """Per-type open button. Stores service directly (discord.py #10335 workaround)."""

    def __init__(self, *, type_id: str, service: TicketService) -> None:
        super().__init__(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_open_{type_id}",
        )
        self._type_id = type_id
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket_type = self._service.type_registry.get(self._type_id)
        if not ticket_type or not ticket_type.enabled:
            await interaction.response.send_message(
                view=status_layout("That ticket type is no longer available."),
                ephemeral=True,
            )
            return

        open_of_type = [
            t
            for t in self._service.active_tickets.values()
            if t.record.creator.id == interaction.user.id
            and t.record.ticket_type == self._type_id
        ]
        if len(open_of_type) >= ticket_type.max_open_per_user:
            await interaction.response.send_message(
                view=status_layout(
                    f"You already have an open **{ticket_type.display_name}** ticket.\n"
                    "Resolve it before opening another."
                ),
                ephemeral=True,
            )
            return

        modal = ticket_type.build_creation_modal(
            callback=lambda intr, meta: self._service.create_ticket(
                intr, self._type_id, meta
            )
        )
        if modal is not None:
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            ticket = await self._service.create_ticket(interaction, self._type_id, {})
            if ticket:
                await interaction.followup.send(
                    view=status_layout(f"Ticket created: {ticket.channel.mention}"),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    view=status_layout("Failed to create ticket. Please try again."),
                    ephemeral=True,
                )


def build_panel_layout(
    service: TicketService, *, header_filename: str | None = None
) -> TicketPanelLayoutView:
    return TicketPanelLayoutView(service=service, header_filename=header_filename)


class TicketPanelLayoutView(discord.ui.LayoutView):
    """Persistent panel - rebuilt whenever types are enabled/disabled."""

    def __init__(self, *, service: TicketService, header_filename: str | None = None) -> None:
        super().__init__(timeout=None)
        enabled = service.type_registry.get_enabled()

        children: list[discord.ui.Item] = [
            *header_items(header_filename),
            discord.ui.TextDisplay(content="## Iron Foundry - Support & Tickets"),
            discord.ui.Separator(),
        ]

        for i, ticket_type in enumerate(enabled):
            children.append(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=(
                            f"**{ticket_type.emoji} {ticket_type.display_name}**\n"
                            f"{ticket_type.description}"
                        )
                    ),
                    accessory=_TicketOpenButton(
                        type_id=ticket_type.identifier, service=service
                    ),
                )
            )
            if i < len(enabled) - 1:
                children.append(discord.ui.Separator())

        if not enabled:
            children.append(
                discord.ui.TextDisplay(
                    content="No ticket types are currently available."
                )
            )

        now_ts = int(datetime.now(UTC).timestamp())
        children.extend(
            [
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    content=f"-# Tickets close after 24h of inactivity · Last updated <t:{now_ts}:R>"
                ),
            ]
        )

        self.add_item(
            discord.ui.Container(*children, accent_colour=discord.Color.gold())
        )

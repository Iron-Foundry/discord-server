from __future__ import annotations

import discord
from datetime import datetime, UTC
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from tickets.ticket_service import TicketService


class TicketTypeSelect(discord.ui.Select):
    """Select menu populated dynamically from enabled ticket types."""

    def __init__(self, service: TicketService) -> None:
        self._service = service
        options = [t.build_select_option() for t in service.type_registry.get_enabled()]
        super().__init__(
            custom_id="ticket_panel_select",
            placeholder="Choose a ticket type to open...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        type_id = self.values[0]
        ticket_type = self._service.type_registry.get(type_id)
        if not ticket_type or not ticket_type.enabled:
            await interaction.response.send_message(
                "That ticket type is no longer available.", ephemeral=True
            )
            return

        # Check per-user open ticket limit
        open_of_type = [
            t
            for t in self._service.active_tickets.values()
            if t.record.creator.id == interaction.user.id
            and t.record.ticket_type == type_id
        ]
        if len(open_of_type) >= ticket_type.max_open_per_user:
            await interaction.response.send_message(
                f"You already have an open **{ticket_type.display_name}** ticket. "
                f"Please resolve it before opening another.",
                ephemeral=True,
            )
            return

        # If the type has a creation modal, show it; otherwise create immediately
        modal = ticket_type.build_creation_modal(
            callback=lambda intr, meta: self._service.create_ticket(intr, type_id, meta)
        )
        if modal is not None:
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            ticket = await self._service.create_ticket(interaction, type_id, {})
            if ticket:
                await interaction.followup.send(
                    f"Your ticket has been created: {ticket.channel.mention}",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "Failed to create your ticket. Please try again.", ephemeral=True
                )


class TicketPanelView(discord.ui.View):
    """Persistent panel view. Rebuilt whenever types are enabled/disabled."""

    def __init__(self, service: TicketService) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect(service))


def build_panel_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🎫 Iron Foundry — Support Tickets",
        description=(
            "Need help or want to apply for something? Use the menu below to open a ticket.\n\n"
            "A staff member will assist you as soon as possible.\n"
            "Tickets automatically close after **24 hours** of inactivity."
        ),
        color=discord.Color.blurple(),
        timestamp=datetime.now(UTC),
    )
    embed.set_footer(text=guild.name, icon_url=guild.icon.url if guild.icon else None)
    return embed

"""DM ticket menu - Discord Components V2."""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from features.tickets.models.ticket import TicketRecord, TicketTypeConfig
    from features.tickets.ticket_service import TicketService

_SELECT_TIMEOUT = 120


class _OpenTypeSelect(discord.ui.Select):
    def __init__(
        self,
        service: TicketService,
        member: discord.Member,
        types: list[TicketTypeConfig],
    ) -> None:
        self._service = service
        self._member = member
        options = [
            discord.SelectOption(
                label=t.display_name,
                value=t.identifier,
                description=t.description,
                emoji=t.emoji,
            )
            for t in types
        ]
        super().__init__(
            placeholder="Choose a ticket type...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        type_id = self.values[0]
        ticket_type = self._service.type_registry.get(type_id)
        if not ticket_type or not ticket_type.enabled:
            await interaction.response.send_message(
                "That ticket type is no longer available."
            )
            return
        modal = ticket_type.build_creation_modal(
            callback=lambda intr, meta: self._service.create_ticket(
                intr, type_id, meta, creator_override=self._member
            )
        )
        if modal is not None:
            await interaction.response.send_modal(modal)
            return
        await interaction.response.defer(thinking=True)
        ticket = await self._service.create_ticket(
            interaction, type_id, {}, creator_override=self._member
        )
        if ticket:
            await interaction.followup.send(
                f"Your ticket has been created: {ticket.channel.mention}"
            )
        else:
            await interaction.followup.send(
                "Failed to create ticket. You may already have one open, or please try again."
            )


class _OpenTypeSelectView(discord.ui.View):
    def __init__(
        self,
        service: TicketService,
        member: discord.Member,
        types: list[TicketTypeConfig],
    ) -> None:
        super().__init__(timeout=_SELECT_TIMEOUT)
        self.add_item(_OpenTypeSelect(service, member, types))


class _ReopenSelect(discord.ui.Select):
    def __init__(
        self,
        service: TicketService,
        member: discord.Member,
        tickets: list[TicketRecord],
    ) -> None:
        self._service = service
        self._member = member
        options = [
            discord.SelectOption(
                label=f"#{t.ticket_id:04d} - {t.ticket_type.replace('_', ' ').title()}",
                value=str(t.ticket_id),
                description=f"Opened {t.created_at.strftime('%Y-%m-%d')}",
            )
            for t in tickets
        ]
        super().__init__(
            placeholder="Choose a ticket to reopen...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket_id = int(self.values[0])
        await interaction.response.defer(thinking=True)
        new_channel = await self._service.reopen_ticket(ticket_id, self._member)
        if new_channel:
            await interaction.followup.send(
                f"Ticket **#{ticket_id:04d}** has been reopened: {new_channel.mention}"
            )
        else:
            await interaction.followup.send(
                f"Could not reopen ticket **#{ticket_id:04d}**."
            )


class _ReopenSelectView(discord.ui.View):
    def __init__(
        self,
        service: TicketService,
        member: discord.Member,
        tickets: list[TicketRecord],
    ) -> None:
        super().__init__(timeout=_SELECT_TIMEOUT)
        self.add_item(_ReopenSelect(service, member, tickets))


class _OpenButton(discord.ui.Button):
    def __init__(self, service: TicketService, member: discord.Member) -> None:
        self._service = service
        self._member = member
        super().__init__(label="Open Ticket", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        enabled_types = self._service.type_registry.get_enabled()
        if not enabled_types:
            await interaction.response.send_message(
                "No ticket types are currently available."
            )
            return
        view = _OpenTypeSelectView(self._service, self._member, enabled_types)
        await interaction.response.send_message(
            "Select the type of ticket you'd like to open:", view=view
        )


class _ReopenButton(discord.ui.Button):
    def __init__(self, service: TicketService, member: discord.Member) -> None:
        self._service = service
        self._member = member
        super().__init__(label="Reopen Ticket", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        tickets = await self._service.get_closed_tickets_by_user(
            self._member.id, limit=25
        )
        if not tickets:
            await interaction.followup.send("You have no closed tickets to reopen.")
            return
        view = _ReopenSelectView(self._service, self._member, tickets)
        await interaction.followup.send("Select a ticket to reopen:", view=view)


def build_dm_menu_layout(
    service: TicketService, member: discord.Member
) -> DMMenuLayout:
    return DMMenuLayout(service=service, member=member)


class DMMenuLayout(discord.ui.LayoutView):
    """DM ticket menu sent on incoming DM."""

    def __init__(self, *, service: TicketService, member: discord.Member) -> None:
        super().__init__(timeout=300)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    content=(
                        "## Iron Foundry - Ticket Support\n"
                        "Use the buttons below to open a new ticket or reopen a previous one.\n"
                        "Your ticket will be created in the Iron Foundry server."
                    )
                ),
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    _OpenButton(service, member),
                    _ReopenButton(service, member),
                ),
                accent_colour=discord.Color.gold(),
            )
        )

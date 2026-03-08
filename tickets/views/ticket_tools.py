from __future__ import annotations

import io
import discord
from typing import TYPE_CHECKING

from common.ticket_types import TicketTypeId

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService
    from tickets.models.ticket import Ticket, TicketTypeConfig


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


class TicketToolsView(discord.ui.View):
    """Moderator tools panel that can be spawned inside any open ticket channel."""

    def __init__(
        self, service: TicketService, ticket_id: int, ticket_type_id: str = ""
    ) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id
        if ticket_type_id in {TicketTypeId.JOIN_CC.value, TicketTypeId.RANKUP.value}:
            self.add_item(RankDetailsButton(service, ticket_type_id))
        self.add_item(ChangeTypeButton(service, ticket_id))

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


class RankDetailsButton(discord.ui.Button):
    """Posts the configured rank requirement images (and join text) into the channel."""

    def __init__(self, service: TicketService, ticket_type_id: str) -> None:
        self._service = service
        self._ticket_type_id = ticket_type_id
        super().__init__(label="Rank Details", style=discord.ButtonStyle.success, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        config = await self._service.get_rank_details_config()

        files: list[discord.File] = []
        if config.rank_reqs:
            files.append(
                discord.File(
                    io.BytesIO(config.rank_reqs.data),
                    filename=config.rank_reqs.filename,
                )
            )
        if config.rank_upgrades:
            files.append(
                discord.File(
                    io.BytesIO(config.rank_upgrades.data),
                    filename=config.rank_upgrades.filename,
                )
            )

        if not files:
            await interaction.followup.send(
                "Rank details images are not configured. "
                "Use `/ticket setrankimage` to set them.",
                ephemeral=True,
            )
            return

        if interaction.channel is None:
            await interaction.followup.send("Cannot determine channel.", ephemeral=True)
            return

        await interaction.channel.send(files=files)  # type: ignore[union-attr]
        if self._ticket_type_id == TicketTypeId.JOIN_CC.value and config.join_text:
            await interaction.channel.send(config.join_text)  # type: ignore[union-attr]
        await interaction.followup.send("Rank details posted.", ephemeral=True)


class ChangeTypeButton(discord.ui.Button):
    """Sends an ephemeral select menu to reclassify the ticket to a different type."""

    def __init__(self, service: TicketService, ticket_id: int) -> None:
        self._service = service
        self._ticket_id = ticket_id
        super().__init__(
            label="Change Type", style=discord.ButtonStyle.secondary, row=1
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        ticket = self._service.get_ticket_by_id(self._ticket_id)
        if not ticket:
            await interaction.followup.send("Ticket not found.", ephemeral=True)
            return
        current_type = ticket.record.ticket_type
        enabled_types = [
            t
            for t in self._service.type_registry.get_all()
            if t.enabled and t.identifier != current_type
        ]
        if not enabled_types:
            await interaction.followup.send(
                "No other ticket types available.", ephemeral=True
            )
            return
        view = ChangeTypeSelectView(self._service, self._ticket_id, enabled_types)
        await interaction.followup.send(
            "Select the new ticket type:", view=view, ephemeral=True
        )


class ChangeTypeSelect(discord.ui.Select):
    """Drop-down for selecting the new ticket type."""

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
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.change_ticket_type(
            self._ticket_id, self.values[0], interaction.user
        )
        if success:
            await interaction.followup.send("Ticket type updated.", ephemeral=True)
        else:
            await interaction.followup.send(
                "Could not change ticket type.", ephemeral=True
            )


class ChangeTypeSelectView(discord.ui.View):
    """Ephemeral view holding the ChangeTypeSelect drop-down."""

    def __init__(
        self, service: TicketService, ticket_id: int, types: list[TicketTypeConfig]
    ) -> None:
        super().__init__(timeout=60)
        self.add_item(ChangeTypeSelect(service, ticket_id, types))


def build_tools_embed() -> discord.Embed:
    return discord.Embed(
        title="🛠️ Ticket Tools",
        description=(
            "Staff tools for managing this ticket.\n"
            "Use `/ticket add` and `/ticket remove` to manage members."
        ),
        color=discord.Color.orange(),
    )

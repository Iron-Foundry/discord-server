from __future__ import annotations

import discord
from collections.abc import Callable, Coroutine
from typing import Any

from core.common.ticket_types import TicketTypeId
from features.tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord
from features.tickets.views._layout_helpers import header_items


class ContactMentorModal(discord.ui.Modal, title="Contact a Mentor"):
    rsn = discord.ui.TextInput(
        label="RuneScape Name (RSN)",
        placeholder="Your exact in-game name",
        max_length=12,
    )
    content = discord.ui.TextInput(
        label="What do you need help with?",
        placeholder="e.g. Chambers of Xeric, Theatre of Blood, a specific boss...",
        max_length=100,
    )
    experience = discord.ui.TextInput(
        label="Experience with this content",
        placeholder="e.g. Never tried it, done it a few times, struggling with a specific mechanic...",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    def __init__(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> None:
        super().__init__()
        self._callback = callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        metadata = {
            "rsn": self.rsn.value,
            "content": self.content.value,
            "experience": self.experience.value,
        }
        ticket = await self._callback(interaction, metadata)
        if ticket:
            await interaction.followup.send(
                f"Your ticket has been created: {ticket.channel.mention}",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Failed to create your ticket. You may already have one open, or please try again.",
                ephemeral=True,
            )


class ContactMentorTicket(TicketTypeConfig):
    """Ticket for getting in contact with a mentor for Raids & PVM help."""

    default_frozen: bool = True

    def __init__(self, mentor_role_id: int, staff_role_id: int) -> None:
        self._teams = [
            TicketTeam(name="Mentors", role_id=mentor_role_id),
            TicketTeam(name="Staff", role_id=staff_role_id),
        ]
        self._db_overrides: dict = {}

    @property
    def identifier(self) -> str:
        return TicketTypeId.CONTACT_MENTOR.value

    @property
    def display_name(self) -> str:
        return self._db_overrides.get("display_name", "Contact a Mentor")

    @property
    def description(self) -> str:
        return self._db_overrides.get("description", "Get help from a mentor with Raids & PVM.")

    @property
    def emoji(self) -> str:
        return self._db_overrides.get("emoji", "⚔️")

    @property
    def color(self) -> discord.Color:
        return discord.Color.purple()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "pvm"

    @property
    def category_name(self) -> str:
        return "PVM Help"

    def build_creation_modal(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> discord.ui.Modal | None:
        return ContactMentorModal(callback)

    def build_create_layout(
        self,
        record: TicketRecord,
        *,
        header_attachment: str | None = None,
        rank_images: dict[str, str] | None = None,
    ) -> discord.ui.LayoutView:
        meta = record.metadata
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                *header_items(header_attachment),
                discord.ui.TextDisplay(
                    content=(
                        f"## {self.emoji} PVM Help - #{record.ticket_id:04d}\n"
                        f"**Player:** <@{record.creator.id}>\n"
                        f"**RSN:** {meta.get('rsn', '-')}\n"
                        f"**Content:** {meta.get('content', '-')}\n"
                        f"**Experience:** {meta.get('experience', '-')}"
                        + (f"\n\n{self.welcome_text}" if self.welcome_text else "")
                        + "\n\n-# A mentor will be with you shortly."
                    )
                ),
                accent_colour=self.color,
            )
        )
        return view

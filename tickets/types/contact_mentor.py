import discord
from collections.abc import Callable, Coroutine
from datetime import datetime, UTC
from typing import Any

from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord


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
        label="Your experience with this content or similar content.",
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
        metadata = {
            "rsn": self.rsn.value,
            "content": self.content.value,
            "experience": self.experience.value,
        }
        await self._callback(interaction, metadata)


class ContactMentorTicket(TicketTypeConfig):
    """Ticket for getting in contact with a mentor for Raids & PVM help."""

    def __init__(self, mentor_role_id: int, staff_role_id: int) -> None:
        self._teams = [
            TicketTeam(name="Mentors", role_id=mentor_role_id),
            TicketTeam(name="Staff", role_id=staff_role_id),
        ]

    @property
    def identifier(self) -> str:
        return TicketTypeId.CONTACT_MENTOR.value

    @property
    def display_name(self) -> str:
        return "Contact a Mentor"

    @property
    def description(self) -> str:
        return "Get help from a mentor with Raids & PVM."

    @property
    def emoji(self) -> str:
        return "⚔️"

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

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        meta = record.metadata
        embed = discord.Embed(
            title=f"{self.emoji} PVM Help — #{record.ticket_id:04d}",
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Player", value=f"<@{record.creator.id}>", inline=True)
        embed.add_field(name="RSN", value=meta.get("rsn", "—"), inline=True)
        embed.add_field(name="Content", value=meta.get("content", "—"), inline=False)
        embed.add_field(
            name="Experience", value=meta.get("experience", "—"), inline=False
        )
        embed.set_footer(
            text="A mentor will be with you shortly. This ticket will auto-close after 24 hours of inactivity."
        )
        return embed

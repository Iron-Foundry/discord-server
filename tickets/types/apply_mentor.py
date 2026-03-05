import discord
from collections.abc import Callable, Coroutine
from datetime import datetime, UTC
from typing import Any

from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord


class ApplyMentorModal(discord.ui.Modal, title="Mentor Application"):
    rsn = discord.ui.TextInput(
        label="RuneScape Name (RSN)",
        placeholder="Your exact in-game name",
        max_length=12,
    )
    experience = discord.ui.TextInput(
        label="OSRS Experience",
        placeholder="e.g. 2000 total, maxed combat, end-game PvM...",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )
    reason = discord.ui.TextInput(
        label="Why do you want to be a mentor?",
        placeholder="Describe how you would help members learn and what content you would want to mentor for.",
        style=discord.TextStyle.paragraph,
        max_length=1000,
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
            "experience": self.experience.value,
            "reason": self.reason.value,
        }
        await self._callback(interaction, metadata)


class ApplyMentorTicket(TicketTypeConfig):
    """Mentor application ticket."""

    def __init__(self, staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Staff", role_id=staff_role_id)]

    @property
    def identifier(self) -> str:
        return TicketTypeId.APPLY_MENTOR.value

    @property
    def display_name(self) -> str:
        return "Apply to Mentor"

    @property
    def description(self) -> str:
        return "Apply to become a mentor."

    @property
    def emoji(self) -> str:
        return "📚"

    @property
    def color(self) -> discord.Color:
        return discord.Color.teal()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "mentor"

    @property
    def category_name(self) -> str:
        return "Mentor Applications"

    def build_creation_modal(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> discord.ui.Modal | None:
        return ApplyMentorModal(callback)

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        meta = record.metadata
        embed = discord.Embed(
            title=f"{self.emoji} Mentor Application — #{record.ticket_id:04d}",
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Applicant", value=f"<@{record.creator.id}>", inline=True)
        embed.add_field(name="RSN", value=meta.get("rsn", "—"), inline=True)
        embed.add_field(
            name="Experience", value=meta.get("experience", "—"), inline=False
        )
        embed.add_field(name="Motivation", value=meta.get("reason", "—"), inline=False)
        embed.set_footer(
            text="This ticket will auto-close after 24 hours of inactivity."
        )
        return embed

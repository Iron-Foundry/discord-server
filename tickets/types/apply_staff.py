import discord
from collections.abc import Callable, Coroutine
from datetime import datetime, UTC
from typing import Any

from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord


class ApplyStaffModal(discord.ui.Modal, title="Staff Application"):
    rsn = discord.ui.TextInput(
        label="RuneScape Name (RSN)",
        placeholder="Your exact in-game name",
        max_length=12,
    )
    experience = discord.ui.TextInput(
        label="Experience",
        placeholder="e.g. 2 years moderating Discord servers",
        max_length=200,
    )
    region = discord.ui.TextInput(
        label="Region",
        placeholder="North America, Europe, Oceania, Asia, South America, Africa / Middle East",
        max_length=30,
    )
    reason = discord.ui.TextInput(
        label="Why do you want to be staff?",
        placeholder="Tell us about your experience and motivation.",
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
            "region": self.region.value,
            "reason": self.reason.value,
        }
        await self._callback(interaction, metadata)


class ApplyStaffTicket(TicketTypeConfig):
    """Staff application ticket."""

    def __init__(self, senior_staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Senior Staff", role_id=senior_staff_role_id)]

    @property
    def identifier(self) -> str:
        return TicketTypeId.APPLY_STAFF.value

    @property
    def display_name(self) -> str:
        return "Apply to Staff"

    @property
    def description(self) -> str:
        return "Apply to become a staff member."

    @property
    def emoji(self) -> str:
        return "🛡️"

    @property
    def color(self) -> discord.Color:
        return discord.Color.red()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "staff"

    @property
    def category_name(self) -> str:
        return "Staff Applications"

    def build_creation_modal(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> discord.ui.Modal | None:
        return ApplyStaffModal(callback)

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        meta = record.metadata
        embed = discord.Embed(
            title=f"{self.emoji} Staff Application — #{record.ticket_id:04d}",
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Applicant", value=f"<@{record.creator.id}>", inline=True)
        embed.add_field(name="RSN", value=meta.get("rsn", "—"), inline=True)
        embed.add_field(
            name="Experience", value=meta.get("experience", "—"), inline=True
        )
        embed.add_field(name="Region", value=meta.get("region", "—"), inline=True)
        embed.add_field(name="Motivation", value=meta.get("reason", "—"), inline=False)
        embed.set_footer(
            text="This ticket will auto-close after 24 hours of inactivity."
        )
        return embed

import discord
from collections.abc import Callable, Coroutine
from datetime import datetime, UTC
from typing import Any

from common.ranks import RANK_OPTIONS
from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord


class RankupModal(discord.ui.Modal, title="Rank Up Application"):
    current_rank = discord.ui.Select(
        placeholder="Current rank...",
        options=RANK_OPTIONS,
        min_values=1,
        max_values=1,
        required=True,
    )
    target_rank = discord.ui.Select(
        placeholder="Applying for...",
        options=RANK_OPTIONS,
        min_values=1,
        max_values=1,
        required=True,
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
            "current_rank": self.current_rank.values[0],
            "target_rank": self.target_rank.values[0],
        }
        await self._callback(interaction, metadata)


class RankupTicket(TicketTypeConfig):
    """Rank-up application ticket."""

    def __init__(self, staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Staff", role_id=staff_role_id)]

    @property
    def identifier(self) -> str:
        return TicketTypeId.RANKUP.value

    @property
    def display_name(self) -> str:
        return "Rank Up"

    @property
    def description(self) -> str:
        return "Apply for a rank based on your OSRS achievements."

    @property
    def emoji(self) -> str:
        return "⬆️"

    @property
    def color(self) -> discord.Color:
        return discord.Color.gold()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "rankup"

    @property
    def category_name(self) -> str:
        return "Rank Applications"

    def build_creation_modal(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> discord.ui.Modal | None:
        return RankupModal(callback)

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        meta = record.metadata
        embed = discord.Embed(
            title=f"{self.emoji} Rank Up Application — #{record.ticket_id:04d}",
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Applicant", value=f"<@{record.creator.id}>", inline=True)
        embed.add_field(
            name="Current Rank", value=meta.get("current_rank", "—"), inline=True
        )
        embed.add_field(
            name="Applying For", value=meta.get("target_rank", "—"), inline=True
        )
        embed.set_footer(
            text="This ticket will auto-close after 24 hours of inactivity."
        )
        return embed

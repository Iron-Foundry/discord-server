import discord
from datetime import datetime, UTC

from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord


class JoinCCTicket(TicketTypeConfig):
    """Application to join the clan chat."""

    def __init__(self, staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Staff", role_id=staff_role_id)]

    @property
    def identifier(self) -> str:
        return TicketTypeId.JOIN_CC.value

    @property
    def display_name(self) -> str:
        return "Join the CC"

    @property
    def description(self) -> str:
        return "Apply to join the Iron Foundry clan chat."

    @property
    def emoji(self) -> str:
        return "🏰"

    @property
    def color(self) -> discord.Color:
        return discord.Color.green()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "join"

    @property
    def category_name(self) -> str:
        return "Join Applications"

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.emoji} Join Application — #{record.ticket_id:04d}",
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Applicant", value=f"<@{record.creator.id}>", inline=True)
        embed.set_footer(
            text="This ticket will auto-close after 24 hours of inactivity."
        )
        return embed

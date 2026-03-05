import discord
from datetime import datetime, UTC

from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord


class GeneralTicket(TicketTypeConfig):
    """General / miscellaneous support ticket."""

    def __init__(self, staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Staff", role_id=staff_role_id)]

    @property
    def identifier(self) -> str:
        return TicketTypeId.GENERAL.value

    @property
    def display_name(self) -> str:
        return "General Support"

    @property
    def description(self) -> str:
        return "General questions and miscellaneous requests."

    @property
    def emoji(self) -> str:
        return "💬"

    @property
    def color(self) -> discord.Color:
        return discord.Color.blurple()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "general"

    @property
    def category_name(self) -> str:
        return "Tickets"

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.emoji} General Support — Ticket #{record.ticket_id:04d}",
            description=(
                "Welcome! A staff member will be with you shortly.\n\n"
                "Please describe your question or issue below."
            ),
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Opened by", value=f"<@{record.creator.id}>", inline=True)
        embed.set_footer(
            text="This ticket will auto-close after 24 hours of inactivity."
        )
        return embed

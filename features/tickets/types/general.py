from __future__ import annotations

import discord

from core.common.ticket_types import TicketTypeId
from features.tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord
from features.tickets.views._layout_helpers import header_items


class GeneralTicket(TicketTypeConfig):
    """General / miscellaneous support ticket."""

    def __init__(self, staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Staff", role_id=staff_role_id)]
        self._db_overrides: dict = {}

    @property
    def identifier(self) -> str:
        return TicketTypeId.GENERAL.value

    @property
    def display_name(self) -> str:
        return self._db_overrides.get("display_name", "General Support")

    @property
    def description(self) -> str:
        return self._db_overrides.get("description", "General questions and miscellaneous requests.")

    @property
    def emoji(self) -> str:
        return self._db_overrides.get("emoji", "💬")

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

    def build_create_layout(
        self,
        record: TicketRecord,
        *,
        header_attachment: str | None = None,
        rank_images: dict[str, str] | None = None,
    ) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                *header_items(header_attachment),
                discord.ui.TextDisplay(
                    content=(
                        f"## {self.emoji} General Support - Ticket #{record.ticket_id:04d}\n"
                        f"Welcome <@{record.creator.id}>!"
                        + (f"\n\n{self.welcome_text}" if self.welcome_text else "")
                        + "\n\n-# This ticket will auto-close after 24 hours of inactivity."
                    )
                ),
                accent_colour=self.color,
            )
        )
        return view

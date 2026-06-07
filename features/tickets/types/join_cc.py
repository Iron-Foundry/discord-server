from __future__ import annotations

import discord

from core.common.ticket_types import TicketTypeId
from features.tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord
from features.tickets.views._layout_helpers import header_items


class JoinCCTicket(TicketTypeConfig):
    """Application to join the clan chat."""

    def __init__(self, staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Staff", role_id=staff_role_id)]
        self._db_overrides: dict = {}

    @property
    def identifier(self) -> str:
        return TicketTypeId.JOIN_CC.value

    @property
    def display_name(self) -> str:
        return self._db_overrides.get("display_name", "Join the CC")

    @property
    def description(self) -> str:
        return self._db_overrides.get("description", "Apply to join the Iron Foundry clan chat.")

    @property
    def emoji(self) -> str:
        return self._db_overrides.get("emoji", "🏰")

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

    def build_create_layout(
        self,
        record: TicketRecord,
        *,
        header_attachment: str | None = None,
        rank_images: dict[str, str] | None = None,
    ) -> discord.ui.LayoutView:
        welcome = self.welcome_text or (
            "To process your application we need screenshots of "
            "`all items/requirements in the rank tier you are going for or upgrades thereof.`"
        )
        view = discord.ui.LayoutView(timeout=None)
        children: list[discord.ui.Item] = [
            *header_items(header_attachment),
            discord.ui.TextDisplay(
                content=(
                    f"## {self.emoji} Join Application - #{record.ticket_id:04d}\n"
                    f"**Applicant:** <@{record.creator.id}>\n\n"
                    f"{welcome}\n\n"
                    "-# This ticket will auto-close after 24 hours of inactivity."
                )
            ),
        ]
        if rank_images:
            if fn := rank_images.get("rank_reqs"):
                children.append(discord.ui.Separator())
                children.append(discord.ui.TextDisplay(content="### Rank Structure:"))
                children.append(
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            media=discord.UnfurledMediaItem(url=f"attachment://{fn}")
                        )
                    )
                )
            if fn := rank_images.get("rank_upgrades"):
                children.append(discord.ui.Separator())
                children.append(discord.ui.TextDisplay(content="### Valid Item & Requirement Upgrades:"))
                children.append(
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            media=discord.UnfurledMediaItem(url=f"attachment://{fn}")
                        )
                    )
                )
        view.add_item(discord.ui.Container(*children, accent_colour=self.color))
        return view

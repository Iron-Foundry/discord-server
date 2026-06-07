from __future__ import annotations

import discord
from collections.abc import Callable, Coroutine
from typing import Any

from core.common.ticket_types import TicketTypeId
from features.tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord
from features.tickets.views._layout_helpers import header_items

_RANK_HINT = "Sapphire, Emerald, Ruby, Diamond, Dragonstone, Onyx, Zenyte"


class RankupModal(discord.ui.Modal, title="Rank Up Application"):
    current_rank = discord.ui.TextInput(
        label="Current Rank",
        placeholder=_RANK_HINT,
        max_length=20,
    )
    target_rank = discord.ui.TextInput(
        label="Applying For",
        placeholder=_RANK_HINT,
        max_length=20,
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
            "current_rank": self.current_rank.value,
            "target_rank": self.target_rank.value,
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


class RankupTicket(TicketTypeConfig):
    """Rank-up application ticket."""

    def __init__(self, staff_role_id: int) -> None:
        self._teams = [TicketTeam(name="Staff", role_id=staff_role_id)]
        self._db_overrides: dict = {}

    @property
    def identifier(self) -> str:
        return TicketTypeId.RANKUP.value

    @property
    def display_name(self) -> str:
        return self._db_overrides.get("display_name", "Rank Up")

    @property
    def description(self) -> str:
        return self._db_overrides.get("description", "Apply for a rank based on your OSRS achievements.")

    @property
    def emoji(self) -> str:
        return self._db_overrides.get("emoji", "⬆️")

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

    def build_create_layout(
        self,
        record: TicketRecord,
        *,
        header_attachment: str | None = None,
        rank_images: dict[str, str] | None = None,
    ) -> discord.ui.LayoutView:
        meta = record.metadata
        welcome = self.welcome_text or (
            "To process your application we need screenshots of "
            "`all items/requirements in the rank tier you are going for or upgrades thereof.`"
        )
        view = discord.ui.LayoutView(timeout=None)
        children: list[discord.ui.Item] = [
            *header_items(header_attachment),
            discord.ui.TextDisplay(
                content=(
                    f"## {self.emoji} Rank Up Application - #{record.ticket_id:04d}\n"
                    f"**Applicant:** <@{record.creator.id}>\n"
                    f"**Current Rank:** {meta.get('current_rank', '-')}\n"
                    f"**Applying For:** {meta.get('target_rank', '-')}\n\n"
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

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from discord import ButtonStyle

from docket.models import DocketPanelRecord

if TYPE_CHECKING:
    from docket.service import DocketService


class AchievementsView(discord.ui.View):
    """Persistent Prev/Next pagination view for the achievements panel."""

    def __init__(
        self,
        service: Any,
        record: DocketPanelRecord,
        total_pages: int,
    ) -> None:
        super().__init__(timeout=None)
        self._service: DocketService = service
        self._record = record
        self.prev_button.disabled = record.current_page == 0
        self.next_button.disabled = record.current_page >= total_pages - 1

    @discord.ui.button(
        label="◀ Previous",
        style=ButtonStyle.secondary,
        custom_id="docket_achievements_prev",
    )
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer()
        await self._service.achievements_page(self._record.current_page - 1)

    @discord.ui.button(
        label="Next ▶",
        style=ButtonStyle.secondary,
        custom_id="docket_achievements_next",
    )
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer()
        await self._service.achievements_page(self._record.current_page + 1)

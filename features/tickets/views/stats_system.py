"""Interactive /ticket system layout - Discord Components V2."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from features.tickets.charts import build_system_chart
from features.tickets.models.stats import SystemStats
from features.tickets.views.stats_shared import (
    _PERIOD_OPTIONS,
    fmt_seconds,
    parse_period,
    period_label,
)

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


def _system_text(stats: SystemStats, period: str) -> str:
    label = period_label(period)
    lines = [
        "**Ticket System Overview**",
        f"Period: {label}",
        (
            f"Opened: **{stats.total_opened}** · "
            f"Closed: **{stats.total_closed}** · "
            f"Currently Open: **{stats.currently_open}**"
        ),
        (
            f"Avg Response: **{fmt_seconds(stats.avg_response_seconds)}** · "
            f"Avg Resolution: **{fmt_seconds(stats.avg_resolution_seconds)}**"
        ),
    ]
    if stats.type_breakdown:
        breakdown = "  ".join(
            f"`{t.replace('_', ' ').title()}`: {c}"
            for t, c in sorted(stats.type_breakdown.items(), key=lambda x: -x[1])
        )
        lines.append(f"**Types:** {breakdown}")
    return "\n".join(lines)


class SystemStatsView(discord.ui.LayoutView):
    """Interactive /ticket system - period select."""

    def __init__(
        self,
        service: TicketService,
        stats: SystemStats,
        period: str = "all",
        chart: discord.File | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self._service = service
        self._period = period

        select = discord.ui.Select(placeholder="Period", options=_PERIOD_OPTIONS)
        select.callback = self._on_period_change

        media_items = []
        if chart:
            media_items.append(
                discord.MediaGalleryItem(
                    media=discord.UnfurledMediaItem(url="attachment://system.png")
                )
            )

        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(content=_system_text(stats, period)),
        ]
        if media_items:
            children.append(discord.ui.Separator())
            children.append(discord.ui.MediaGallery(*media_items))
        children.append(discord.ui.Separator())
        children.append(discord.ui.ActionRow(select))

        self.add_item(discord.ui.Container(*children))

    async def _on_period_change(self, interaction: discord.Interaction) -> None:
        data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
        values: list[str] = data.get("values", [])
        if not values:
            await interaction.response.defer()
            return
        self._period = values[0]
        since = parse_period(self._period)
        try:
            stats = await self._service.get_system_stats(since)
        except Exception as e:
            logger.error(f"SystemStatsView: get_system_stats failed: {e}")
            await interaction.response.defer()
            return
        chart = await build_system_chart(stats, self._period)
        new_view = SystemStatsView(self._service, stats, self._period, chart)
        await interaction.response.edit_message(
            view=new_view, attachments=[chart] if chart else []
        )

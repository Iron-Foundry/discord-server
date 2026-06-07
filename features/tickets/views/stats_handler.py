"""Interactive /ticket stats layout - Discord Components V2."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from features.tickets.charts import build_stats_chart
from features.tickets.models.stats import HandlerStats
from features.tickets.views.stats_shared import (
    _PERIOD_OPTIONS,
    fmt_seconds,
    parse_period,
    period_label,
)

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


def _stats_text(stats: HandlerStats | None, display_name: str, period: str) -> str:
    label = period_label(period)
    if stats is None:
        return f"**Ticket Stats - {display_name}**\nPeriod: {label}\n\nNo closed tickets found."
    lines = [
        f"**Ticket Stats - {display_name}**",
        f"Period: {label}",
        f"Closed: **{stats.tickets_closed}** · Participated: **{stats.tickets_participated}**",
        f"Avg Response: **{fmt_seconds(stats.avg_response_seconds)}** · "
        f"Avg Resolution: **{fmt_seconds(stats.avg_resolution_seconds)}**",
    ]
    if stats.type_breakdown:
        breakdown = "  ".join(
            f"`{t.replace('_', ' ').title()}`: {c}"
            for t, c in sorted(stats.type_breakdown.items(), key=lambda x: -x[1])
        )
        lines.append(f"**Types:** {breakdown}")
    return "\n".join(lines)


class StatsView(discord.ui.LayoutView):
    """Interactive /ticket stats - period select."""

    def __init__(
        self,
        service: TicketService,
        staff_id: int,
        display_name: str,
        stats: HandlerStats | None,
        period: str = "all",
        chart: discord.File | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self._service = service
        self._staff_id = staff_id
        self._display_name = display_name
        self._period = period

        select = discord.ui.Select(placeholder="Period", options=_PERIOD_OPTIONS)
        select.callback = self._on_period_change

        media_items = []
        if chart:
            media_items.append(
                discord.MediaGalleryItem(
                    media=discord.UnfurledMediaItem(url="attachment://stats.png")
                )
            )

        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(content=_stats_text(stats, display_name, period)),
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
            stats = await self._service.get_handler_stats(self._staff_id, since)
        except Exception as e:
            logger.error(f"StatsView: get_handler_stats failed: {e}")
            await interaction.response.defer()
            return
        chart = (
            await build_stats_chart(stats, self._display_name, self._period)
            if stats
            else None
        )
        new_view = StatsView(
            self._service,
            self._staff_id,
            self._display_name,
            stats,
            self._period,
            chart,
        )
        await interaction.response.edit_message(
            view=new_view, attachments=[chart] if chart else []
        )

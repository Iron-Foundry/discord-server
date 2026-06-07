"""Interactive /ticket leaderboard layout - Discord Components V2."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from features.tickets.charts import build_leaderboard_chart
from features.tickets.models.stats import LeaderboardEntry
from features.tickets.views.stats_shared import (
    _PERIOD_OPTIONS,
    fmt_seconds,
    parse_period,
    period_label,
)

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


def _leaderboard_text(
    entries: list[LeaderboardEntry],
    names: dict[int, str],
    period: str,
    metric: str,
) -> str:
    label = period_label(period)
    if not entries:
        return f"**Ticket Leaderboard**\nPeriod: {label}\n\nNo data found."
    lines = ["**Ticket Leaderboard**", f"Period: {label}"]
    for e in entries:
        name = names.get(e.staff_id, f"<@{e.staff_id}>")
        if metric == "resolution":
            stat = f"Avg Resolution: **{fmt_seconds(e.avg_resolution_seconds)}**"
        elif metric == "participated":
            stat = f"Participated: **{e.tickets_participated}**"
        else:
            stat = f"Closed: **{e.tickets_closed}**"
        lines.append(f"#{e.rank} {name} - {stat}")
    return "\n".join(lines)


def _resolve_names(
    entries: list[LeaderboardEntry], guild: discord.Guild | None
) -> dict[int, str]:
    if guild is None:
        return {}
    return {
        e.staff_id: (
            m.display_name
            if (m := guild.get_member(e.staff_id)) is not None
            else f"<@{e.staff_id}>"
        )
        for e in entries
    }


class LeaderboardView(discord.ui.LayoutView):
    """Interactive /ticket leaderboard - period + metric select."""

    def __init__(
        self,
        service: TicketService,
        entries: list[LeaderboardEntry],
        names: dict[int, str],
        period: str = "30d",
        metric: str = "closed",
        chart: discord.File | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self._service = service
        self._period = period
        self._metric = metric

        period_select = discord.ui.Select(placeholder="Period", options=_PERIOD_OPTIONS)
        period_select.callback = self._on_period_change

        metric_select = discord.ui.Select(
            placeholder="Metric",
            options=[
                discord.SelectOption(label="Tickets Closed", value="closed"),
                discord.SelectOption(label="Avg Resolution Time", value="resolution"),
                discord.SelectOption(
                    label="Tickets Participated In", value="participated"
                ),
            ],
        )
        metric_select.callback = self._on_metric_change

        media_items = []
        if chart:
            media_items.append(
                discord.MediaGalleryItem(
                    media=discord.UnfurledMediaItem(url="attachment://leaderboard.png")
                )
            )

        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(
                content=_leaderboard_text(entries, names, period, metric)
            ),
        ]
        if media_items:
            children.append(discord.ui.Separator())
            children.append(discord.ui.MediaGallery(*media_items))
        children.extend(
            [discord.ui.Separator(), discord.ui.ActionRow(period_select, metric_select)]
        )
        self.add_item(discord.ui.Container(*children))

    async def _fetch_and_edit(self, interaction: discord.Interaction) -> None:
        since = parse_period(self._period)
        try:
            entries = await self._service.get_leaderboard(since, metric=self._metric)
        except Exception as e:
            logger.error(f"LeaderboardView: get_leaderboard failed: {e}")
            await interaction.response.defer()
            return
        names = _resolve_names(entries, interaction.guild)
        chart = await build_leaderboard_chart(
            entries, names, self._metric, self._period
        )
        new_view = LeaderboardView(
            self._service, entries, names, self._period, self._metric, chart
        )
        await interaction.response.edit_message(
            view=new_view, attachments=[chart] if chart else []
        )

    async def _on_period_change(self, interaction: discord.Interaction) -> None:
        data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
        values: list[str] = data.get("values", [])
        if not values:
            await interaction.response.defer()
            return
        self._period = values[0]
        await self._fetch_and_edit(interaction)

    async def _on_metric_change(self, interaction: discord.Interaction) -> None:
        data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
        values: list[str] = data.get("values", [])
        if not values:
            await interaction.response.defer()
            return
        self._metric = values[0]
        await self._fetch_and_edit(interaction)

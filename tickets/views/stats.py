"""Interactive Discord UI views for /ticket stats and /ticket leaderboard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from tickets.models.stats import HandlerStats, LeaderboardEntry, SystemStats

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService

_PERIOD_DAYS: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}

_PERIOD_OPTIONS = [
    discord.SelectOption(label="Last 7 days", value="7d"),
    discord.SelectOption(label="Last 30 days", value="30d"),
    discord.SelectOption(label="Last 90 days", value="90d"),
    discord.SelectOption(label="All time", value="all"),
]


def _parse_period(period: str) -> datetime | None:
    days = _PERIOD_DAYS.get(period)
    return datetime.now(UTC) - timedelta(days=days) if days else None


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}h {m}m" if h else f"{m}m"


def _build_stats_embed(
    stats: HandlerStats, display_name: str, period: str
) -> discord.Embed:
    period_label = {
        "7d": "Last 7 days",
        "30d": "Last 30 days",
        "90d": "Last 90 days",
        "all": "All time",
    }.get(period, period)

    embed = discord.Embed(
        title=f"Ticket Stats — {display_name}",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Period", value=period_label, inline=True)
    embed.add_field(name="Tickets Closed", value=str(stats.tickets_closed), inline=True)
    embed.add_field(
        name="Tickets Participated In",
        value=str(stats.tickets_participated),
        inline=True,
    )
    embed.add_field(
        name="Avg Response Time",
        value=_fmt_seconds(stats.avg_response_seconds),
        inline=True,
    )
    embed.add_field(
        name="Avg Resolution Time",
        value=_fmt_seconds(stats.avg_resolution_seconds),
        inline=True,
    )
    if stats.type_breakdown:
        breakdown_lines = [
            f"`{t.replace('_', ' ').title()}`: {c}"
            for t, c in sorted(stats.type_breakdown.items(), key=lambda x: -x[1])
        ]
        embed.add_field(
            name="Type Breakdown", value="\n".join(breakdown_lines), inline=False
        )
    return embed


def _build_leaderboard_embed(
    entries: list[LeaderboardEntry],
    names: dict[int, str],
    period: str,
    metric: str,
) -> discord.Embed:
    period_label = {
        "7d": "Last 7 days",
        "30d": "Last 30 days",
        "90d": "Last 90 days",
        "all": "All time",
    }.get(period, period)

    embed = discord.Embed(
        title="Ticket Leaderboard",
        description=f"Period: **{period_label}**",
        color=discord.Color.blurple(),
    )

    if not entries:
        embed.description = f"Period: **{period_label}**\n\nNo data found."
        return embed

    for entry in entries:
        name = names.get(entry.staff_id, f"<@{entry.staff_id}>")
        if metric == "resolution":
            value = f"Avg Resolution: **{_fmt_seconds(entry.avg_resolution_seconds)}**"
        else:
            value = f"Tickets Closed: **{entry.tickets_closed}**"
        embed.add_field(
            name=f"#{entry.rank} — {name}",
            value=value,
            inline=False,
        )
    return embed


class StatsView(discord.ui.View):
    """Interactive view for /ticket stats — period select.

    Updating the embed on period change. The chart image (sent with the
    initial response) is preserved by discord.py automatically since
    edit_message does not touch attachments unless explicitly instructed.
    """

    def __init__(
        self,
        service: TicketService,
        staff_id: int,
        display_name: str,
        period: str = "all",
    ) -> None:
        super().__init__(timeout=300)
        self._service = service
        self._staff_id = staff_id
        self._display_name = display_name
        self._period = period

        period_select = discord.ui.Select(
            placeholder="Period",
            options=_PERIOD_OPTIONS,
            row=0,
        )
        period_select.callback = self._on_period_change
        self.add_item(period_select)

    async def _on_period_change(self, interaction: discord.Interaction) -> None:
        data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
        values: list[str] = data.get("values", [])
        if not values:
            await interaction.response.defer()
            return
        self._period = values[0]
        since = _parse_period(self._period)

        try:
            stats = await self._service.get_handler_stats(self._staff_id, since)
        except Exception as e:
            logger.error(f"StatsView: get_handler_stats failed: {e}")
            await interaction.response.defer()
            return

        if stats is None:
            embed = discord.Embed(
                title=f"Ticket Stats — {self._display_name}",
                description="No closed tickets found for this period.",
                color=discord.Color.blurple(),
            )
        else:
            embed = _build_stats_embed(stats, self._display_name, self._period)

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore[union-attr]


class LeaderboardView(discord.ui.View):
    """Interactive view for /ticket leaderboard — period select + metric select.

    The chart image from the initial response is preserved automatically.
    """

    def __init__(
        self,
        service: TicketService,
        period: str = "30d",
        metric: str = "closed",
    ) -> None:
        super().__init__(timeout=300)
        self._service = service
        self._period = period
        self._metric = metric

        period_select = discord.ui.Select(
            placeholder="Period",
            options=_PERIOD_OPTIONS,
            row=0,
        )
        period_select.callback = self._on_period_change
        self.add_item(period_select)

        metric_select = discord.ui.Select(
            placeholder="Metric",
            options=[
                discord.SelectOption(label="Tickets Closed", value="closed"),
                discord.SelectOption(label="Avg Resolution Time", value="resolution"),
            ],
            row=1,
        )
        metric_select.callback = self._on_metric_change
        self.add_item(metric_select)

    async def _fetch_and_edit(self, interaction: discord.Interaction) -> None:
        since = _parse_period(self._period)
        try:
            entries = await self._service.get_leaderboard(since)
        except Exception as e:
            logger.error(f"LeaderboardView: get_leaderboard failed: {e}")
            await interaction.response.defer()
            return

        names = self._resolve_names(entries, interaction.guild)
        embed = _build_leaderboard_embed(entries, names, self._period, self._metric)
        await interaction.response.edit_message(embed=embed, view=self)

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

    def _resolve_names(
        self,
        entries: list[LeaderboardEntry],
        guild: discord.Guild | None,
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

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore[union-attr]


def _build_system_embed(stats: SystemStats, period: str) -> discord.Embed:
    """Build the embed for /ticket system."""
    period_label = {
        "7d": "Last 7 days",
        "30d": "Last 30 days",
        "90d": "Last 90 days",
        "all": "All time",
    }.get(period, period)

    embed = discord.Embed(
        title="Ticket System Overview",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Period", value=period_label, inline=True)
    embed.add_field(name="Tickets Opened", value=str(stats.total_opened), inline=True)
    embed.add_field(name="Tickets Closed", value=str(stats.total_closed), inline=True)
    embed.add_field(name="Currently Open", value=str(stats.currently_open), inline=True)
    embed.add_field(
        name="Avg Response Time",
        value=_fmt_seconds(stats.avg_response_seconds),
        inline=True,
    )
    embed.add_field(
        name="Avg Resolution Time",
        value=_fmt_seconds(stats.avg_resolution_seconds),
        inline=True,
    )
    if stats.type_breakdown:
        breakdown_lines = [
            f"`{t.replace('_', ' ').title()}`: {c}"
            for t, c in sorted(stats.type_breakdown.items(), key=lambda x: -x[1])
        ]
        embed.add_field(
            name="Type Breakdown", value="\n".join(breakdown_lines), inline=False
        )
    return embed


class SystemStatsView(discord.ui.View):
    """Interactive view for /ticket system — period select."""

    def __init__(self, service: TicketService, period: str = "all") -> None:
        super().__init__(timeout=300)
        self._service = service
        self._period = period

        period_select = discord.ui.Select(
            placeholder="Period",
            options=_PERIOD_OPTIONS,
            row=0,
        )
        period_select.callback = self._on_period_change
        self.add_item(period_select)

    async def _on_period_change(self, interaction: discord.Interaction) -> None:
        data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
        values: list[str] = data.get("values", [])
        if not values:
            await interaction.response.defer()
            return
        self._period = values[0]
        since = _parse_period(self._period)

        try:
            stats = await self._service.get_system_stats(since)
        except Exception as e:
            logger.error(f"SystemStatsView: get_system_stats failed: {e}")
            await interaction.response.defer()
            return

        embed = _build_system_embed(stats, self._period)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True  # type: ignore[union-attr]

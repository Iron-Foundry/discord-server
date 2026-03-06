from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import discord

from docket.models import DocketPanelRecord, PanelType
from docket.panels.base import DocketPanel
from docket.providers.protocol import ExternalApiProvider

_PAGE_SIZE = 10
_ORANGE = discord.Color.orange()


def _format_achievement(raw: dict[str, Any]) -> tuple[str, str]:
    """Return (name, value) strings for an achievement embed field."""
    player_name: str = raw.get("player", {}).get("displayName", "Unknown")
    metric: str = raw.get("metric", "unknown").replace("_", " ").title()
    measure: str = raw.get("measure", "")
    threshold = raw.get("threshold", 0)

    if measure == "levels":
        value = f"Reached level **{threshold}** in **{metric}**"
    elif measure == "rank":
        value = f"Achieved rank **{threshold}** in **{metric}**"
    else:
        value = f"**{metric}** · {measure} {threshold}"

    return player_name, value


class AchievementsPanel(DocketPanel):
    """Panel showing recent clan achievements fetched from Wise Old Man."""

    panel_type = PanelType.ACHIEVEMENTS
    display_name = "Clan Achievements"
    refresh_interval_seconds = 3600  # hourly

    def __init__(self, provider: ExternalApiProvider, wom_group_id: int) -> None:
        self._provider = provider
        self._wom_group_id = wom_group_id
        self._cached: list[dict[str, Any]] = []
        self._last_updated: datetime | None = None

    def _total_pages(self) -> int:
        if not self._cached:
            return 1
        return max(1, (len(self._cached) + _PAGE_SIZE - 1) // _PAGE_SIZE)

    async def build_embeds(self, record: DocketPanelRecord) -> list[discord.Embed]:
        """Build a single paginated embed of achievements."""
        embed = discord.Embed(title="Clan Achievements", color=_ORANGE)

        if not self._cached:
            embed.description = "Loading achievements..."
            return [embed]

        total_pages = self._total_pages()
        page = max(0, min(record.current_page, total_pages - 1))
        start = page * _PAGE_SIZE
        slice_ = self._cached[start : start + _PAGE_SIZE]

        for raw in slice_:
            name, value = _format_achievement(raw)
            embed.add_field(name=name, value=value, inline=True)

        ts_str = (
            f"<t:{int(self._last_updated.timestamp())}:R>"
            if self._last_updated
            else "never"
        )
        embed.set_footer(text=f"Page {page + 1}/{total_pages} · Last updated {ts_str}")
        return [embed]

    def build_view(
        self, record: DocketPanelRecord, service: Any
    ) -> discord.ui.View | None:
        from docket.views.achievements_view import AchievementsView

        return AchievementsView(
            service=service,
            record=record,
            total_pages=self._total_pages(),
        )

    async def refresh(self, record: DocketPanelRecord) -> DocketPanelRecord:
        """Fetch fresh achievements from WOM and update the in-memory cache."""
        data = await self._provider.fetch(limit=20)
        self._cached = data
        self._last_updated = datetime.now(UTC)
        return record

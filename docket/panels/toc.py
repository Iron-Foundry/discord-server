from __future__ import annotations

import discord

from docket.models import DocketPanelRecord, PanelType
from docket.panels.base import DocketPanel

_BLURPLE = discord.Color.blurple()


class TOCPanel(DocketPanel):
    """Panel showing the server guide / table of contents."""

    panel_type = PanelType.TOC
    display_name = "Server Guide"
    refresh_interval_seconds = 0

    async def build_embeds(self, record: DocketPanelRecord) -> list[discord.Embed]:
        """Build a single embed with a numbered channel list."""
        embed = discord.Embed(title="Server Guide", color=_BLURPLE)
        if not record.toc_entries:
            embed.description = "No entries yet."
            return [embed]

        sorted_entries = sorted(record.toc_entries, key=lambda e: e.position)
        lines = [
            f"{i + 1}. <#{e.channel_id}> — {e.description}"
            for i, e in enumerate(sorted_entries)
        ]
        embed.description = "\n".join(lines)
        return [embed]

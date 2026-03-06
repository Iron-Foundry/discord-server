from __future__ import annotations

import discord

from docket.models import DocketPanelRecord, PanelType
from docket.panels.base import DocketPanel

_MAX_EVENTS = 10
_GOLD = discord.Color.gold()


class EventsPanel(DocketPanel):
    """Panel showing upcoming and running clan events."""

    panel_type = PanelType.EVENTS
    display_name = "Events"
    refresh_interval_seconds = 0

    async def build_embeds(self, record: DocketPanelRecord) -> list[discord.Embed]:
        """Build one embed per event (up to 10), or a placeholder if none."""
        if not record.event_entries:
            embed = discord.Embed(
                title="Clan Events",
                description="No events currently running.",
                color=_GOLD,
            )
            return [embed]

        embeds: list[discord.Embed] = []
        for entry in record.event_entries[:_MAX_EVENTS]:
            embed = discord.Embed(
                title=entry.title,
                description=entry.description or None,
                color=_GOLD,
            )
            if entry.host:
                embed.add_field(name="Host", value=entry.host, inline=True)
            if entry.starts_at:
                ts = int(entry.starts_at.timestamp())
                embed.add_field(name="Starts", value=f"<t:{ts}:R>", inline=True)
            if entry.ends_at:
                ts = int(entry.ends_at.timestamp())
                embed.add_field(name="Ends", value=f"<t:{ts}:R>", inline=True)
            if entry.image_url:
                embed.set_image(url=entry.image_url)
            embeds.append(embed)
        return embeds

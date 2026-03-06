from __future__ import annotations

import discord

from docket.models import DocketPanelRecord, PanelType
from docket.panels.base import DocketPanel

_MAX_ENTRIES = 15
_GREEN = discord.Color.green()


class DonationsPanel(DocketPanel):
    """Panel showing recent clan donations."""

    panel_type = PanelType.DONATIONS
    display_name = "Clan Donations"
    refresh_interval_seconds = 0

    async def build_embeds(self, record: DocketPanelRecord) -> list[discord.Embed]:
        """Build a single embed with the most recent 15 donations."""
        embed = discord.Embed(title="Clan Donations", color=_GREEN)
        if not record.donation_entries:
            embed.description = "No donations recorded yet."
            return [embed]

        sorted_entries = sorted(
            record.donation_entries,
            key=lambda e: e.donated_at,
            reverse=True,
        )
        for entry in sorted_entries[:_MAX_ENTRIES]:
            ts = int(entry.donated_at.timestamp())
            value_parts = [entry.amount]
            if entry.note:
                value_parts.append(entry.note)
            value_parts.append(f"<t:{ts}:R>")
            embed.add_field(
                name=entry.donor_name,
                value=" · ".join(value_parts),
                inline=True,
            )
        return [embed]

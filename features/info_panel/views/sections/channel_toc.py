from __future__ import annotations

import discord

from features.info_panel.models import ChannelTocSection


def build(section: ChannelTocSection, live_data: dict, guild: discord.Guild) -> list[discord.ui.Item]:
    if not section.channels:
        return []

    lines: list[str] = ["## Channels", ""]

    for entry in section.channels:
        mention = f"<#{entry.channel_id}>"
        if entry.description:
            lines.append(f"{mention} - {entry.description}")
        else:
            lines.append(mention)

    return [discord.ui.TextDisplay(content="\n".join(lines))]

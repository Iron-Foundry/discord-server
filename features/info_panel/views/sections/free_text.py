from __future__ import annotations

import discord

from features.info_panel.models import FreeTextSection


def build(section: FreeTextSection, live_data: dict, guild: discord.Guild) -> list[discord.ui.Item]:
    if not section.content.strip():
        return []
    return [discord.ui.TextDisplay(content=section.content)]

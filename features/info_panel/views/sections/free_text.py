from __future__ import annotations

from typing import Any

import discord

from features.info_panel.models import FreeTextSection


def build(
    section: FreeTextSection, live_data: dict[str, Any], guild: discord.Guild
) -> list[discord.ui.Item[Any]]:
    if not section.content.strip():
        return []
    return [discord.ui.TextDisplay(content=section.content)]

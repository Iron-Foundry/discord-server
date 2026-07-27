from __future__ import annotations

from typing import Any

import discord

from features.info_panel.models import WebsiteLinksSection


def build(
    section: WebsiteLinksSection, live_data: dict[str, Any], guild: discord.Guild
) -> list[discord.ui.Item[Any]]:
    items: list[discord.ui.Item[Any]] = [
        discord.ui.TextDisplay(content="## Links & Info"),
    ]
    if not section.links:
        items.append(discord.ui.TextDisplay(content="*No links configured.*"))
        return items

    buttons: list[discord.ui.Button[Any]] = [
        discord.ui.Button(
            label=link.label[:80],
            url=link.url,
            style=discord.ButtonStyle.link,
        )
        for link in section.links[:5]  # ActionRow supports max 5 buttons
    ]
    items.append(discord.ui.ActionRow(*buttons))
    return items

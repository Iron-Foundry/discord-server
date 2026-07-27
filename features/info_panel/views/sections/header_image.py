from __future__ import annotations

from typing import Any

import discord

from features.info_panel.models import HeaderImageSection


def build(
    section: HeaderImageSection, live_data: dict[str, Any], guild: discord.Guild
) -> list[discord.ui.Item[Any]]:
    if not section.image_url:
        return []
    items: list[discord.ui.Item[Any]] = [
        discord.ui.MediaGallery(
            discord.MediaGalleryItem(
                media=discord.UnfurledMediaItem(url=section.image_url)
            )
        ),
    ]
    return items

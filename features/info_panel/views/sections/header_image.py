from __future__ import annotations

import discord

from features.info_panel.models import HeaderImageSection


def build(section: HeaderImageSection, live_data: dict, guild: discord.Guild) -> list[discord.ui.Item]:
    if not section.image_url:
        return []
    items: list[discord.ui.Item] = [
        discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=discord.UnfurledMediaItem(url=section.image_url))
        ),
    ]
    return items

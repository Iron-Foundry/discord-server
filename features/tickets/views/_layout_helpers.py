"""Shared Components V2 layout utilities for ticket views."""

from __future__ import annotations

import discord


def status_layout(content: str) -> discord.ui.LayoutView:
    """Minimal ephemeral status/error/success message as a LayoutView."""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(content=content),
        )
    )
    return view


def header_items(attachment_filename: str | None) -> list[discord.ui.Item]:
    """Returns a single-image MediaGallery if a filename is provided, else empty list.

    Pass the result as leading *args to discord.ui.Container so the header image
    appears above all other children:

        discord.ui.Container(*header_items(filename), TextDisplay(...), ...)
    """
    if not attachment_filename:
        return []
    return [
        discord.ui.MediaGallery(
            discord.MediaGalleryItem(
                media=discord.UnfurledMediaItem(
                    url=f"attachment://{attachment_filename}"
                )
            )
        )
    ]

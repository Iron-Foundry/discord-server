"""Assembles LayoutViews from panel config and live data."""

from __future__ import annotations

import discord

from features.info_panel.models import (
    AchievementsSection,
    ChannelTocSection,
    CompetitionsSection,
    FreeTextSection,
    HeaderImageSection,
    InfoPanelConfig,
    NameChangesSection,
    PersonalBestsSection,
    ServerStatsSection,
    WebsiteLinksSection,
)
from features.info_panel.views.sections import (
    achievements,
    channel_toc,
    competitions,
    free_text,
    header_image,
    name_changes,
    personal_bests,
    server_stats,
    website_links,
)

_ACCENT = discord.Color.from_str("#C8A951")  # gold


def _build_section_items(
    section: object,
    live_data: dict,
    guild: discord.Guild,
) -> list[discord.ui.Item]:
    if isinstance(section, HeaderImageSection):
        return header_image.build(section, live_data, guild)
    if isinstance(section, ServerStatsSection):
        return server_stats.build(section, live_data, guild)
    if isinstance(section, FreeTextSection):
        return free_text.build(section, live_data, guild)
    if isinstance(section, ChannelTocSection):
        return channel_toc.build(section, live_data, guild)
    if isinstance(section, NameChangesSection):
        return name_changes.build(section, live_data, guild)
    if isinstance(section, AchievementsSection):
        return achievements.build(section, live_data, guild)
    if isinstance(section, WebsiteLinksSection):
        return website_links.build(section, live_data, guild)
    if isinstance(section, PersonalBestsSection):
        return personal_bests.build(section, live_data, guild)
    if isinstance(section, CompetitionsSection):
        return competitions.build(section, live_data, guild)
    return []


def build_views(
    config: InfoPanelConfig,
    live_data: dict,
    guild: discord.Guild,
) -> list[discord.ui.LayoutView]:
    """Return one LayoutView per message in config.messages."""
    views: list[discord.ui.LayoutView] = []

    for panel_message in config.messages:
        container_items: list[discord.ui.Item] = []
        top_level_rows: list[discord.ui.ActionRow] = []

        for section in panel_message.sections:
            section_items = _build_section_items(section, live_data, guild)
            if not section_items:
                continue

            non_rows = [it for it in section_items if not isinstance(it, discord.ui.ActionRow)]
            rows = [it for it in section_items if isinstance(it, discord.ui.ActionRow)]

            if container_items and non_rows:
                container_items.append(discord.ui.Separator())
            container_items.extend(non_rows)
            top_level_rows.extend(rows)

        if not container_items and not top_level_rows:
            continue

        view = discord.ui.LayoutView(timeout=None)
        if container_items:
            view.add_item(discord.ui.Container(*container_items, accent_colour=_ACCENT))
        for row in top_level_rows:
            view.add_item(row)

        views.append(view)

    return views

from __future__ import annotations

from enum import StrEnum

import discord
from pydantic import BaseModel, Field


class LogCategory(StrEnum):
    """Categories for action log forum threads."""

    MESSAGES = "messages"
    MEMBERS = "members"
    ROLES = "roles"
    CHANNELS = "channels"
    GUILD = "guild"
    MODERATION = "moderation"
    SCHEDULED = "scheduled-events"
    INVITES = "invites"


CATEGORY_LABELS: dict[LogCategory, str] = {
    LogCategory.MESSAGES: "Messages",
    LogCategory.MEMBERS: "Members",
    LogCategory.ROLES: "Roles",
    LogCategory.CHANNELS: "Channels",
    LogCategory.GUILD: "Guild",
    LogCategory.MODERATION: "Moderation",
    LogCategory.SCHEDULED: "Scheduled Events",
    LogCategory.INVITES: "Invites",
}

CATEGORY_COLORS: dict[LogCategory, discord.Color] = {
    LogCategory.MESSAGES: discord.Color.gold(),
    LogCategory.MEMBERS: discord.Color.green(),
    LogCategory.ROLES: discord.Color.blue(),
    LogCategory.CHANNELS: discord.Color.purple(),
    LogCategory.GUILD: discord.Color.teal(),
    LogCategory.MODERATION: discord.Color.red(),
    LogCategory.SCHEDULED: discord.Color.orange(),
    LogCategory.INVITES: discord.Color.dark_green(),
}


class ActionLogConfig(BaseModel):
    """Persisted configuration for the action log service."""

    guild_id: int
    forum_channel_id: int | None = None
    thread_ids: dict[str, int] = Field(
        default_factory=dict
    )  # category.value → thread_id
    ignored_channel_ids: list[int] = Field(default_factory=list)
    ignored_thread_ids: list[int] = Field(default_factory=list)
    ignored_category_ids: list[int] = Field(default_factory=list)
    enabled: bool = True

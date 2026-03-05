from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from core.discord_client import DiscordClient

from action_log.models import (
    ActionLogConfig,
    CATEGORY_LABELS,
    LogCategory,
)
from action_log.registrar import EventRegistrar
from action_log.repository import MongoActionLogRepository
from action_log.throttle import MessageThrottle


class ActionLogService:
    """
    Coordinates the action log forum channel.

    Responsibilities:
    - Load/persist config from MongoDB
    - Set up forum threads per log category
    - Route log embeds through the rate-limited throttle
    - Manage ignore lists and enabled state
    - Register event handlers on the Discord client
    """

    def __init__(
        self,
        guild: discord.Guild,
        client: DiscordClient,
        repo: MongoActionLogRepository,
    ) -> None:
        self._guild = guild
        self._client = client
        self._repo = repo
        self._config: ActionLogConfig | None = None
        self._throttle = MessageThrottle()
        self._registrar = EventRegistrar(self)

    async def initialize(self) -> None:
        """Load config, register events, and start the throttle."""
        await self._repo.ensure_indexes()
        self._config = await self._repo.get_config(self._guild.id)

        from action_log.events import register_all_events

        register_all_events(self._registrar)
        self._registrar.register_on(self._client)
        self._throttle.start(self._client)
        logger.info("ActionLogService initialised")

    async def post(self, category: LogCategory, embed: discord.Embed) -> None:
        """Enqueue an embed to the category's forum thread."""
        if not self._config or not self._config.enabled:
            return
        thread_id = self._config.thread_ids.get(category.value)
        if thread_id is None:
            return
        await self._throttle.enqueue(thread_id, embed)

    def is_ignored(self, channel_id: int, *, parent_id: int | None = None) -> bool:
        """Return True if the channel or parent thread is on the ignore list."""
        if not self._config:
            return False
        if channel_id in self._config.ignored_channel_ids:
            return True
        if parent_id is not None and parent_id in self._config.ignored_thread_ids:
            return True
        return False

    async def setup_forum(self, forum: discord.ForumChannel) -> ActionLogConfig:
        """
        Create or reuse a thread for each log category in the forum.

        Active threads whose name matches a category label are reused;
        all others are created fresh. Returns the updated config.
        """
        config = self._config or ActionLogConfig(guild_id=self._guild.id)
        config.forum_channel_id = forum.id

        active_by_name: dict[str, discord.Thread] = {
            t.name: t for t in forum.threads if not t.archived
        }

        for category in LogCategory:
            label = CATEGORY_LABELS[category]
            thread = active_by_name.get(label)
            if thread:
                config.thread_ids[category.value] = thread.id
                logger.info(f"ActionLog: reused thread '{label}' ({thread.id})")
            else:
                new_thread, _ = await forum.create_thread(
                    name=label,
                    content=f"Action log — **{label}**",
                )
                config.thread_ids[category.value] = new_thread.id
                logger.info(f"ActionLog: created thread '{label}' ({new_thread.id})")

        self._config = config
        await self._repo.save_config(config)
        return config

    async def add_ignore(self, channel_id: int, *, is_thread: bool) -> bool:
        """Add a channel or thread to the ignore list. Returns True if added."""
        if not self._config:
            return False
        target = (
            self._config.ignored_thread_ids
            if is_thread
            else self._config.ignored_channel_ids
        )
        if channel_id in target:
            return False
        target.append(channel_id)
        await self._repo.save_config(self._config)
        return True

    async def remove_ignore(self, channel_id: int, *, is_thread: bool) -> bool:
        """Remove a channel or thread from the ignore list. Returns True if removed."""
        if not self._config:
            return False
        target = (
            self._config.ignored_thread_ids
            if is_thread
            else self._config.ignored_channel_ids
        )
        if channel_id not in target:
            return False
        target.remove(channel_id)
        await self._repo.save_config(self._config)
        return True

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable the action log. Returns True if the state changed."""
        if not self._config:
            return False
        if self._config.enabled == enabled:
            return False
        self._config.enabled = enabled
        await self._repo.save_config(self._config)
        return True

    @property
    def config(self) -> ActionLogConfig | None:
        """Current action log config, or None if not yet configured."""
        return self._config

    @property
    def guild(self) -> discord.Guild:
        """The guild this action log monitors."""
        return self._guild

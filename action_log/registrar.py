from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from action_log.service import ActionLogService
    from core.discord_client import DiscordClient


class EventRegistrar:
    """Collects event handlers and registers them on a Discord client."""

    def __init__(self, service: ActionLogService) -> None:
        self._service = service
        self._handlers: list[tuple[str, Callable[..., Coroutine[Any, Any, None]]]] = []

    @property
    def service(self) -> ActionLogService:
        """The action log service, used by event modules to post entries."""
        return self._service

    def add(
        self,
        event_name: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
    ) -> None:
        """Append an event handler to the registry."""
        self._handlers.append((event_name, handler))

    def register_on(self, client: DiscordClient) -> None:
        """Attach all registered handlers to the Discord client."""
        for event_name, handler in self._handlers:
            client.add_listener(handler, event_name)
        logger.info(f"EventRegistrar: registered {len(self._handlers)} event handlers")

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar

from . import (
    channels,
    guild,
    invites,
    members,
    messages,
    moderation,
    roles,
    scheduled,
    threads,
)


def register_all_events(registrar: EventRegistrar) -> None:
    """Register all event handlers with the registrar."""
    messages.register(registrar)
    members.register(registrar)
    roles.register(registrar)
    channels.register(registrar)
    threads.register(registrar)
    guild.register(registrar)
    moderation.register(registrar)
    scheduled.register(registrar)
    invites.register(registrar)

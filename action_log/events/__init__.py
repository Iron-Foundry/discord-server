from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register_all_events(registrar: EventRegistrar) -> None:
    """Register all event handlers. Event modules will be added here incrementally."""
    pass

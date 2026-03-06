from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExternalApiProvider(Protocol):
    """Protocol for external data source providers used by docket panels."""

    provider_id: str  # stable identifier, e.g. "wise_old_man"

    async def start(self) -> None:
        """Open sessions, authenticate. Called once on service initialize."""
        ...

    async def stop(self) -> None:
        """Close sessions. Called on graceful shutdown."""
        ...

    async def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return raw data. kwargs are provider-specific (limit, metric, etc.)"""
        ...

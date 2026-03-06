from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

_BASE_URL = "https://api.wiseoldman.net/v2"


class WiseOldManProvider:
    """Fetches clan achievement data from the Wise Old Man API."""

    provider_id = "wise_old_man"

    def __init__(self, group_id: int) -> None:
        self._group_id = group_id
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Open the HTTP session."""
        self._http = httpx.AsyncClient(base_url=_BASE_URL, timeout=10.0)

    async def stop(self) -> None:
        """Close the HTTP session."""
        if self._http:
            await self._http.aclose()
            self._http = None

    async def fetch(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch recent group achievements from WOM.

        Supported kwargs:
            limit (int): max results to return, default 20.
        """
        if not self._http:
            logger.warning("WiseOldManProvider: fetch called before start()")
            return []
        limit = kwargs.get("limit", 20)
        try:
            response = await self._http.get(
                f"/groups/{self._group_id}/achievements",
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"WiseOldManProvider: HTTP error {exc.response.status_code} "
                f"fetching achievements"
            )
        except httpx.RequestError as exc:
            logger.warning(f"WiseOldManProvider: request error: {exc}")
        return []

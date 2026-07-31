"""Report provisioned ids back to api-backend, which owns the tile race tables."""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

_TIMEOUT = 15


async def report_result(event_id: str, result: dict[str, Any]) -> bool:
    """POST the created (or cleared) ids for one event. Returns success."""
    api_url = os.getenv("API_BACKEND_URL", "").rstrip("/")
    api_key = os.getenv("METRICS_API_KEY", "")
    if not api_url or not api_key:
        logger.warning(
            "tilerace: API_BACKEND_URL or METRICS_API_KEY not set - cannot report ids"
        )
        return False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            response = await http.post(
                f"{api_url}/tilerace/events/{event_id}/discord/result",
                json=result,
                headers={"verification-code": api_key},
            )
    except Exception as exc:
        logger.warning(
            "tilerace: failed to report ids for event {} - {}", event_id, exc
        )
        return False
    if response.status_code >= 400:
        logger.warning(
            "tilerace: result for event {} returned HTTP {} - {}",
            event_id,
            response.status_code,
            response.text,
        )
        return False
    return True

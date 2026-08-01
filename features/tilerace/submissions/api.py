"""Service-key calls to api-backend, which owns every tile race table."""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger

_TIMEOUT = 15


class ApiUnavailableError(RuntimeError):
    """api-backend could not be reached or refused the call."""


def _credentials() -> tuple[str, str]:
    api_url = os.getenv("API_BACKEND_URL", "").rstrip("/")
    api_key = os.getenv("METRICS_API_KEY", "")
    if not api_url or not api_key:
        raise ApiUnavailableError("API_BACKEND_URL or METRICS_API_KEY is not set")
    return api_url, api_key


async def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    api_url, api_key = _credentials()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            response = await http.request(
                method,
                f"{api_url}{path}",
                headers={"verification-code": api_key},
                **kwargs,
            )
    except httpx.HTTPError as exc:
        logger.warning("tilerace submissions: {} {} failed - {}", method, path, exc)
        raise ApiUnavailableError(str(exc)) from exc
    if response.status_code >= 400:
        detail = _detail(response)
        logger.info(
            "tilerace submissions: {} {} returned HTTP {} - {}",
            method,
            path,
            response.status_code,
            detail,
        )
        raise ApiUnavailableError(detail)
    return dict(response.json())


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(payload, dict) and payload.get("detail"):
        return str(payload["detail"])
    return f"HTTP {response.status_code}"


async def get_context(discord_user_id: int) -> dict[str, Any]:
    """The caller's team, the tile it stands on, and which leaves need proof."""
    return await _request(
        "GET",
        "/tilerace/submissions/context",
        params={"discord_user_id": str(discord_user_id)},
    )


async def create(
    event_id: str,
    discord_user_id: int,
    path_position: int,
    leaf_keys: list[str],
    proof_urls: list[str],
    thread_id: int,
) -> dict[str, Any]:
    return await _request(
        "POST",
        f"/tilerace/events/{event_id}/submissions",
        json={
            "discord_user_id": str(discord_user_id),
            "path_position": path_position,
            "leaf_keys": leaf_keys,
            "proof_urls": proof_urls,
            "discord_thread_id": str(thread_id),
        },
    )


async def review(
    event_id: str,
    thread_id: int,
    status: str,
    reviewer_id: int,
    notes: str | None = None,
) -> dict[str, Any]:
    """Give every submission made in one thread the same verdict."""
    return await _request(
        "POST",
        f"/tilerace/events/{event_id}/submissions/threads/{thread_id}/review",
        json={
            "status": status,
            "review_notes": notes,
            "reviewed_by": str(reviewer_id),
        },
    )

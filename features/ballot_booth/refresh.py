"""Debounced ballot poll message refresh, coalescing bursts of votes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from loguru import logger

from features.ballot_booth.views import BallotBoothView

if TYPE_CHECKING:
    from features.ballot_booth.pg_repository import PgBallotRepository

_DEBOUNCE_SECONDS = 3.0
_pending: dict[int, asyncio.Task] = {}


async def _do_refresh(
    run_id: int,
    message: discord.Message,
    repo: PgBallotRepository,
    vote_cost: int,
) -> None:
    context = await repo.get_poll_context(run_id)
    if context is None:
        return
    view = BallotBoothView(
        run_id=run_id,
        title=context["title"],
        options=context["options"],
        vote_cost=vote_cost,
        poll_ends_unix=context["poll_ends_unix"],
        tallies=await repo.tally(run_id),
    )
    try:
        await message.edit(view=view)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
        logger.warning("ballot refresh: run {} edit failed: {}", run_id, exc)


def schedule_refresh(
    run_id: int,
    message: discord.Message,
    repo: PgBallotRepository,
    vote_cost: int,
) -> None:
    """Schedule one refresh per run within the debounce window (trailing edge)."""
    existing = _pending.get(run_id)
    if existing is not None and not existing.done():
        return

    async def _worker() -> None:
        try:
            await asyncio.sleep(_DEBOUNCE_SECONDS)
            await _do_refresh(run_id, message, repo, vote_cost)
        finally:
            _pending.pop(run_id, None)

    _pending[run_id] = asyncio.create_task(_worker(), name=f"ballot-refresh-{run_id}")

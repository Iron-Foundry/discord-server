"""DB-backed poll provider for the ballot booth (Components V2 + token charge)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from features.ballot_booth.pg_repository import PgBallotRepository
from features.ballot_booth.views import BallotBoothClosedView, BallotBoothView

if TYPE_CHECKING:
    from features.competition_schedule.poll_provider import PollResult


class BallotBoothPollProvider:
    """Posts a ballot booth poll and resolves the winner from DB vote tallies."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._repo = PgBallotRepository(session_factory)

    async def post_poll(
        self,
        channel: discord.TextChannel,
        title: str,
        options: list[dict],
        run_id: int,
        vote_cost: int,
        poll_ends_unix: int | None = None,
    ) -> int:
        view = BallotBoothView(
            run_id=run_id,
            title=title,
            options=options,
            vote_cost=vote_cost,
            poll_ends_unix=poll_ends_unix,
            tallies=await self._repo.tally(run_id),
        )
        msg = await channel.send(view=view)
        return msg.id

    async def update_poll(
        self,
        channel: discord.TextChannel,
        message_id: int,
        run_id: int,
        title: str,
        options: list[dict],
        vote_cost: int,
        poll_ends_unix: int | None,
    ) -> None:
        view = BallotBoothView(
            run_id=run_id,
            title=title,
            options=options,
            vote_cost=vote_cost,
            poll_ends_unix=poll_ends_unix,
            tallies=await self._repo.tally(run_id),
        )
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.warning(
                "BallotBoothPollProvider: could not update message {}: {}",
                message_id,
                exc,
            )

    async def collect_result(
        self,
        channel: discord.TextChannel,
        message_id: int,
        run_id: int,
        options: list[dict],
        title: str,
    ) -> PollResult:
        tally = await self._repo.tally(run_id)
        winner = self._winner(tally, options)
        winner_label = next(
            (o.get("label") for o in options if o.get("metric") == winner), winner
        )
        await self._close_message(
            channel, message_id, title, winner_label if winner else None
        )
        return {"winning_metric": winner}

    @staticmethod
    def _winner(tally: dict[str, int], options: list[dict]) -> str | None:
        if not tally:
            return None
        order = {o.get("metric"): i for i, o in enumerate(options)}
        best_metric, _ = max(
            tally.items(), key=lambda kv: (kv[1], -order.get(kv[0], len(order)))
        )
        return best_metric

    async def _close_message(
        self,
        channel: discord.TextChannel,
        message_id: int,
        title: str,
        winner_label: str | None,
    ) -> None:
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(
                view=BallotBoothClosedView(title=title, winner_label=winner_label)
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.warning(
                "BallotBoothPollProvider: could not close message {}: {}",
                message_id,
                exc,
            )

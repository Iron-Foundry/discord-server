from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import (
    BallotPollVote,
    BallotTokenAccount,
    BallotTokenTransaction,
    CompetitionSchedule,
    ScheduledCompetitionRun,
)
from features.ballot_booth.icons import metric_icon_url


class PgBallotRepository:
    """PostgreSQL persistence for ballot votes and token balances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def _balance(self, session: AsyncSession, discord_user_id: int) -> int:
        result = await session.execute(
            select(BallotTokenAccount.balance).where(
                BallotTokenAccount.discord_user_id == discord_user_id
            )
        )
        return result.scalar_one_or_none() or 0

    async def get_balance(self, discord_user_id: int) -> int:
        """Return a user's current ballot token balance."""
        async with self._factory() as session:
            return await self._balance(session, discord_user_id)

    async def cast_vote(
        self, run_id: int, discord_user_id: int, metric: str, vote_cost: int
    ) -> tuple[str, int]:
        """Record a vote and charge tokens. Returns (status, balance).

        Status is one of ok, changed, unchanged, insufficient. A member is charged
        once per poll; switching to a different option later is free.
        """
        now = datetime.now(UTC)
        async with self._factory() as session:
            inserted = await session.execute(
                pg_insert(BallotPollVote)
                .values(
                    run_id=run_id,
                    discord_user_id=discord_user_id,
                    metric=metric,
                    created_at=now,
                )
                .on_conflict_do_nothing(constraint="uq_ballot_vote_once")
                .returning(BallotPollVote.id)
            )
            if inserted.scalar_one_or_none() is None:
                return await self._change_vote(session, run_id, discord_user_id, metric)

            if vote_cost <= 0:
                await session.commit()
                return "ok", await self._balance(session, discord_user_id)

            debit = await session.execute(
                update(BallotTokenAccount)
                .where(
                    BallotTokenAccount.discord_user_id == discord_user_id,
                    BallotTokenAccount.balance >= vote_cost,
                )
                .values(balance=BallotTokenAccount.balance - vote_cost, updated_at=now)
                .returning(BallotTokenAccount.balance)
            )
            new_balance = debit.scalar_one_or_none()
            if new_balance is None:
                await session.rollback()
                return "insufficient", await self._balance(session, discord_user_id)

            session.add(
                BallotTokenTransaction(
                    discord_user_id=discord_user_id,
                    delta=-vote_cost,
                    reason="vote_spend",
                    run_id=run_id,
                    created_at=now,
                )
            )
            await session.commit()
            logger.info(
                "PgBallotRepository: user {} voted {} in run {}",
                discord_user_id,
                metric,
                run_id,
            )
            return "ok", new_balance

    async def _change_vote(
        self, session: AsyncSession, run_id: int, discord_user_id: int, metric: str
    ) -> tuple[str, int]:
        changed = await session.execute(
            update(BallotPollVote)
            .where(
                BallotPollVote.run_id == run_id,
                BallotPollVote.discord_user_id == discord_user_id,
                BallotPollVote.metric != metric,
            )
            .values(metric=metric)
            .returning(BallotPollVote.id)
        )
        did_change = changed.scalar_one_or_none() is not None
        await session.commit()
        balance = await self._balance(session, discord_user_id)
        return ("changed" if did_change else "unchanged"), balance

    async def get_poll_context(self, run_id: int) -> dict[str, Any] | None:
        """Return the poll title, icon-enriched options, and close time for a run."""
        async with self._factory() as session:
            run = await session.get(ScheduledCompetitionRun, run_id)
            if run is None:
                return None
            sched = await session.get(CompetitionSchedule, run.schedule_id)
            if sched is None:
                return None
            raw_options = run.poll_options_override or sched.poll_options or []
            options = [
                {**opt, "icon_url": metric_icon_url(opt.get("metric", ""))}
                for opt in raw_options
            ]
            ends_unix = int(run.poll_ends_at.timestamp()) if run.poll_ends_at else None
            return {
                "title": sched.name,
                "options": options,
                "poll_ends_unix": ends_unix,
            }

    async def tally(self, run_id: int) -> dict[str, int]:
        """Return vote counts keyed by metric for a run."""
        async with self._factory() as session:
            rows = await session.execute(
                select(BallotPollVote.metric, func.count())
                .where(BallotPollVote.run_id == run_id)
                .group_by(BallotPollVote.metric)
            )
            return dict(rows.tuples().all())

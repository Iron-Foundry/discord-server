from __future__ import annotations

import re
from typing import Any

import discord
from loguru import logger

from features.tickets.views._layout_helpers import status_layout


def vote_custom_id(run_id: int, metric: str, vote_cost: int) -> str:
    """Structured custom_id parsed by the BallotVoteButton dynamic handler."""
    return f"ballot_vote:{run_id}:{metric}:{vote_cost}"


_STATUS_MESSAGES = {
    "ok": "Vote cast for **{metric}**. Ballot Tokens remaining: **{balance}**.",
    "changed": "Vote changed to **{metric}**. No token charged. Balance: **{balance}**.",
    "unchanged": "You already voted for **{metric}**. Balance: **{balance}**.",
    "insufficient": (
        "Not enough Ballot Tokens to vote (cost {cost}, balance **{balance}**)."
    ),
}


class BallotVoteButton(
    discord.ui.DynamicItem[discord.ui.Button[Any]],
    template=r"ballot_vote:(?P<run_id>\d+):(?P<metric>[a-z0-9_\-]+):(?P<cost>\d+)",
):
    """Persistent vote button; charges a ballot token per vote, one vote per poll."""

    def __init__(self, run_id: int, metric: str, vote_cost: int) -> None:
        self.run_id = run_id
        self.metric = metric
        self.vote_cost = vote_cost
        super().__init__(
            discord.ui.Button(
                label=metric.replace("_", " ").title(),
                style=discord.ButtonStyle.primary,
                custom_id=vote_custom_id(run_id, metric, vote_cost),
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
    ) -> BallotVoteButton:
        return cls(
            run_id=int(match["run_id"]),
            metric=match["metric"],
            vote_cost=int(match["cost"]),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        from core.db import get_session_factory
        from features.ballot_booth.pg_repository import PgBallotRepository

        repo = PgBallotRepository(get_session_factory())
        status, balance = await repo.cast_vote(
            self.run_id, interaction.user.id, self.metric, self.vote_cost
        )
        message = _STATUS_MESSAGES[status].format(
            metric=self.metric.replace("_", " ").title(),
            balance=balance,
            cost=self.vote_cost,
        )
        await interaction.followup.send(view=status_layout(message), ephemeral=True)
        if status in ("ok", "changed") and interaction.message is not None:
            from features.ballot_booth.refresh import schedule_refresh

            schedule_refresh(self.run_id, interaction.message, repo, self.vote_cost)
        logger.info(
            "BallotVoteButton: run {} user {} -> {}",
            self.run_id,
            interaction.user.id,
            status,
        )

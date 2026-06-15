"""Poll provider abstraction - swap native Discord polls for a custom implementation."""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol, TypedDict, runtime_checkable

import discord
from loguru import logger


class PollOption(TypedDict):
    label: str
    metric: str


class PollResult(TypedDict):
    winning_metric: str | None  # None means no votes / poll was skipped


@runtime_checkable
class PollProvider(Protocol):
    async def post_poll(
        self,
        channel: discord.TextChannel,
        question: str,
        options: list[PollOption],
        duration_hours: float,
    ) -> int:
        """Post a poll to the channel and return the Discord message ID."""
        ...

    async def collect_result(
        self,
        channel: discord.TextChannel,
        message_id: int,
        options: list[PollOption],
    ) -> PollResult:
        """Fetch the current poll state and return the winning metric (or None if no winner)."""
        ...


class DiscordNativePollProvider:
    """Uses Discord's built-in poll feature (discord.py 2.4+)."""

    async def post_poll(
        self,
        channel: discord.TextChannel,
        question: str,
        options: list[PollOption],
        duration_hours: float,
    ) -> int:
        poll = discord.Poll(
            question=question,
            duration=timedelta(hours=duration_hours),
            multiple=False,
        )
        for opt in options:
            poll.add_answer(text=opt["label"])

        msg = await channel.send(poll=poll)
        return msg.id

    async def collect_result(
        self,
        channel: discord.TextChannel,
        message_id: int,
        options: list[PollOption],
    ) -> PollResult:
        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            logger.info(
                "DiscordNativePollProvider: poll message {} not found (deleted/skipped)",
                message_id,
            )
            return PollResult(winning_metric=None)

        if msg.poll is None:
            return PollResult(winning_metric=None)

        answers = list(msg.poll.answers)
        if not answers or all(a.vote_count == 0 for a in answers):
            return PollResult(winning_metric=None)

        # Match answers back to options by index (poll.add_answer preserves order)
        best_idx = max(range(len(answers)), key=lambda i: answers[i].vote_count)
        if best_idx < len(options):
            return PollResult(winning_metric=options[best_idx]["metric"])
        return PollResult(winning_metric=None)

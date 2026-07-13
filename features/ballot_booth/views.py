"""Components V2 ballot booth poll view."""

from __future__ import annotations

from datetime import datetime, timezone

import discord

from features.ballot_booth.vote_button import vote_custom_id

POLL_BOOTH_ICON_URL = (
    "https://oldschool.runescape.wiki/images/thumb/"
    "Poll_booth_%28forest_green%2C_closed%29.png/"
    "800px-Poll_booth_%28forest_green%2C_closed%29.png?a4b98"
)
_MAX_BALLOT_OPTIONS = 5


def _booth_thumbnail() -> discord.ui.Thumbnail:
    return discord.ui.Thumbnail(
        media=discord.UnfurledMediaItem(url=POLL_BOOTH_ICON_URL)
    )


def _votes_label(count: int) -> str:
    return f"{count} vote" if count == 1 else f"{count} votes"


def _option_items(
    run_id: int, option: dict, vote_cost: int, count: int
) -> list[discord.ui.Item]:
    label = option.get("label", option.get("metric", "?"))
    icon_url = option.get("icon_url", "")
    button = discord.ui.Button(
        label="Vote",
        style=discord.ButtonStyle.primary,
        custom_id=vote_custom_id(run_id, option.get("metric", ""), vote_cost),
    )
    text = discord.ui.TextDisplay(content=f"**{label}**\n-# {_votes_label(count)}")
    header: discord.ui.Item = (
        discord.ui.Section(
            text,
            accessory=discord.ui.Thumbnail(
                media=discord.UnfurledMediaItem(url=icon_url)
            ),
        )
        if icon_url
        else text
    )
    return [header, discord.ui.ActionRow(button)]


def _closes_line(poll_ends_unix: int | None) -> str:
    if not poll_ends_unix:
        return ""
    return f"\nPoll closes <t:{poll_ends_unix}:R> (<t:{poll_ends_unix}:f>)"


class BallotBoothView(discord.ui.LayoutView):
    """Persistent ballot booth poll rendered with Components V2."""

    def __init__(
        self,
        *,
        run_id: int,
        title: str,
        options: list[dict],
        vote_cost: int,
        poll_ends_unix: int | None = None,
        tallies: dict[str, int] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        shown = options[:_MAX_BALLOT_OPTIONS]
        counts = tallies or {}
        total = sum(counts.values())

        header = (
            f"## {title}\n"
            f"Vote for the next competition metric. "
            f"Each vote costs **{vote_cost}** Ballot Token"
            f"{'s' if vote_cost != 1 else ''}. "
            f"You may change your choice for free.\n"
            f"-# {_votes_label(total)} cast"
            f"{_closes_line(poll_ends_unix)}"
        )

        children: list[discord.ui.Item] = [
            discord.ui.Section(
                discord.ui.TextDisplay(content=header),
                accessory=_booth_thumbnail(),
            ),
            discord.ui.Separator(),
        ]
        for option in shown:
            count = counts.get(option.get("metric", ""), 0)
            children.extend(_option_items(run_id, option, vote_cost, count))

        updated_unix = int(datetime.now(tz=timezone.utc).timestamp())
        children.append(discord.ui.Separator())
        children.append(
            discord.ui.TextDisplay(content=f"-# Last updated: <t:{updated_unix}:R>")
        )

        self.add_item(
            discord.ui.Container(*children, accent_colour=discord.Color.gold())
        )


class BallotBoothClosedView(discord.ui.LayoutView):
    """Terminal state shown after a ballot poll closes."""

    def __init__(self, *, title: str, winner_label: str | None) -> None:
        super().__init__(timeout=None)
        result = (
            f"Winner: **{winner_label}**" if winner_label else "No votes were cast."
        )
        self.add_item(
            discord.ui.Container(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        content=f"## {title}\nPoll closed. {result}"
                    ),
                    accessory=_booth_thumbnail(),
                ),
                accent_colour=discord.Color.dark_gold(),
            )
        )

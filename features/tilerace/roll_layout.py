"""The Components V2 card posted to a team's channel after a roll."""

from __future__ import annotations

from typing import Any

import discord

_ACCENT = discord.Color.gold()


def roll_layout(command: dict[str, Any]) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*_children(command), accent_colour=_ACCENT))
    return view


def _children(command: dict[str, Any]) -> list[discord.ui.Item[Any]]:
    tile = command.get("tile") or {}
    children: list[discord.ui.Item[Any]] = [
        discord.ui.TextDisplay(content=_headline(command))
    ]
    if tile:
        children.append(discord.ui.Separator())
        children.append(_tile_block(tile))
        requirements = tile.get("requirements") or []
        if requirements:
            children.append(
                discord.ui.TextDisplay(
                    content="### Requirements\n" + "\n".join(requirements)
                )
            )
    notes = command.get("notes") or []
    if notes:
        children.append(discord.ui.Separator())
        children.append(
            discord.ui.TextDisplay(content="\n".join(f"**{n}**" for n in notes))
        )
    return children


def _headline(command: dict[str, Any]) -> str:
    """Who rolled what, as a mention rather than a bare snowflake."""
    roll = command.get("roll") or {}
    who = f"<@{command.get('rolled_by')}>"
    position = roll.get("new_position")
    if roll.get("skipped"):
        return f"{who} lost the turn to a skip - still on tile **{position}**."
    dice = roll.get("dice") or []
    total = roll.get("total", 0)
    breakdown = f" ({' + '.join(str(d) for d in dice)})" if len(dice) > 1 else ""
    return f"{who} rolled **{total}**{breakdown} and moved to tile **{position}**."


def _tile_block(tile: dict[str, Any]) -> discord.ui.Item[Any]:
    """The tile's title and description, with its icon when it has one."""
    body = discord.ui.TextDisplay(
        content=(
            f"## {tile.get('title') or 'Tile'}\n{tile.get('description') or ''}"
        ).strip()
    )
    icon = tile.get("icon_url")
    if not icon:
        return body
    return discord.ui.Section(body, accessory=discord.ui.Thumbnail(media=icon))

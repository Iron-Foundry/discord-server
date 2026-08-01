"""Components V2 layouts for the submission panel, card, and verdicts."""

from __future__ import annotations

from typing import Any

import discord

_ACCENT = discord.Color.gold()


def status_layout(message: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(content=message), accent_colour=_ACCENT
        )
    )
    return view


def panel_container(button: discord.ui.Button[Any]) -> discord.ui.Container[Any]:
    return discord.ui.Container(
        discord.ui.TextDisplay(
            content=(
                "## Tile Race Submissions\n"
                "Press **Submit** to open a private thread for the tile your "
                "team is standing on. Post your screenshots there, pick which "
                "requirements they prove, then confirm.\n\n"
                "-# You can roll again as soon as you confirm - staff review "
                "afterwards. A rejected submission sends your team back to "
                "that tile until it is redone."
            )
        ),
        discord.ui.Separator(),
        discord.ui.ActionRow(button),
        accent_colour=_ACCENT,
    )


def card_children(
    context: dict[str, Any], captains_mention: str
) -> list[discord.ui.Item[Any]]:
    """The read-only half of a submission card: tile, team, requirement list."""
    tile = context.get("tile") or {}
    team = context.get("team") or {}
    leaves = context.get("leaves") or []
    outstanding = [leaf for leaf in leaves if not leaf.get("covered")]
    lines = "\n".join(
        f"- {'~~' if leaf.get('covered') else ''}{leaf['label']}"
        f"{'~~ (submitted)' if leaf.get('covered') else ''}"
        for leaf in leaves
    )
    return [
        discord.ui.TextDisplay(
            content=(
                f"## {tile.get('title') or 'Tile'}\n"
                f"**Team:** {team.get('name', '-')} - "
                f"tile {context.get('path_position')}\n\n"
                f"{tile.get('description') or ''}"
            ).strip()
        ),
        discord.ui.Separator(),
        discord.ui.TextDisplay(
            content=f"### Requirements ({len(outstanding)} outstanding)\n{lines}"
        ),
        discord.ui.TextDisplay(
            content=(
                "Post your screenshots in this thread, then pick what they "
                f"prove and press Confirm.\n-# {captains_mention}"
            )
        ),
    ]


def submitted_layout(
    result: dict[str, Any], proof_count: int, buttons: list[discord.ui.Button[Any]]
) -> discord.ui.LayoutView:
    """Confirmation of a logged submission, carrying the staff verdict buttons."""
    claimed = result.get("tile_status") in ("claimed", "approved")
    body = (
        "## Submitted\n"
        f"{len(result.get('ids') or [])} requirement(s) logged with "
        f"{proof_count} screenshot(s)."
    )
    body += (
        "\n\n**This tile is now claimed - go roll.**"
        if claimed
        else "\n\nStill missing proof for the rest of this tile, so rolls stay locked."
    )
    body += "\n-# Staff will review below."
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(content=body),
            discord.ui.Separator(),
            discord.ui.ActionRow(*buttons),
            accent_colour=_ACCENT,
        )
    )
    return view


def verdict_layout(
    status: str, reviewer: str, notes: str | None, result: dict[str, Any]
) -> discord.ui.LayoutView:
    approved = status == "approved"
    body = f"## {'Approved' if approved else 'Rejected'}\nReviewed by {reviewer}."
    if notes:
        body += f"\n\n**Reason:** {notes}"
    if not approved:
        body += (
            "\n\nYour team has been sent back to this tile. Redo it and submit "
            "again - your furthest position is handed back once it passes."
        )
    if result.get("reviewed"):
        body += f"\n-# {result['reviewed']} requirement(s) updated."
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(content=body),
            accent_colour=discord.Color.green() if approved else discord.Color.red(),
        )
    )
    return view

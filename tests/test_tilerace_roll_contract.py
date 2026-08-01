"""Guard: the roll-feedback card renders every field api-backend publishes.

api-backend owns the wording of the requirement lines and the landing notes;
the bot only lays them out. Skipped outside the monorepo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from features.tilerace import roll_feed
from features.tilerace.roll_layout import roll_layout

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

pytestmark = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)


def _fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "tilerace_roll.json").read_text())


def _text(view: discord.ui.LayoutView) -> str:
    chunks: list[str] = []
    for item in view.walk_children():
        content = getattr(item, "content", None)
        if isinstance(content, str):
            chunks.append(content)
    return "\n".join(chunks)


def _channel() -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    return channel


def test_the_card_names_the_roller_the_roll_and_the_tile() -> None:
    command = _fixture()["command"]
    body = _text(roll_layout(command))

    assert f"<@{command['rolled_by']}>" in body
    assert "rolled **3** (2 + 1)" in body
    assert "tile **7**" in body
    assert "## Bandos armour" in body
    assert command["tile"]["description"] in body


def test_the_requirement_lines_are_printed_verbatim() -> None:
    command = _fixture()["command"]
    body = _text(roll_layout(command))

    assert "### Requirements" in body
    for line in command["tile"]["requirements"]:
        assert line in body


def test_the_landing_notes_are_printed_verbatim() -> None:
    command = _fixture()["command"]
    assert command["notes"][0] in _text(roll_layout(command))


def test_a_tile_icon_becomes_a_thumbnail() -> None:
    view = roll_layout(_fixture()["command"])
    assert any(isinstance(item, discord.ui.Thumbnail) for item in view.walk_children())


def test_a_tile_without_an_icon_still_renders() -> None:
    command = _fixture()["command"]
    command["tile"]["icon_url"] = None
    body = _text(roll_layout(command))

    assert "## Bandos armour" in body
    assert not any(
        isinstance(item, discord.ui.Thumbnail)
        for item in roll_layout(command).walk_children()
    )


def test_a_skipped_turn_says_so_and_shows_no_tile() -> None:
    body = _text(roll_layout(_fixture()["skipped_command"]))

    assert "lost the turn to a skip" in body
    assert "tile **4**" in body
    assert "### Requirements" not in body


async def test_the_card_is_posted_to_the_channel_the_command_names() -> None:
    command = _fixture()["command"]
    channel = _channel()
    guild = MagicMock()
    guild.get_channel.return_value = channel

    assert await roll_feed.announce(guild, command) is True
    guild.get_channel.assert_called_once_with(int(command["channel_id"]))
    assert isinstance(channel.send.call_args.kwargs["view"], discord.ui.LayoutView)


async def test_a_channel_the_bot_cannot_see_is_not_an_error() -> None:
    guild = MagicMock()
    guild.get_channel.return_value = None

    assert await roll_feed.announce(guild, _fixture()["command"]) is False

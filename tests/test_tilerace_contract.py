"""Guard: the tile race provisioning seam matches the shared contract.

api-backend publishes `command`; this side consumes it and POSTs `result` back.
The monorepo-root fixture pins both shapes. Skipped outside the monorepo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from features.tilerace import naming, perms, provisioning
from features.tilerace.service import _CHANNEL

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

pytestmark = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)


def _fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "tilerace_discord.json").read_text())


def _guild() -> MagicMock:
    guild = MagicMock()
    guild.get_role.return_value = None
    guild.get_channel.return_value = None
    guild.get_member.return_value = None

    def _made(oid: int) -> AsyncMock:
        obj = AsyncMock()
        obj.id = oid
        obj.members = []
        return obj

    guild.create_role = AsyncMock(side_effect=lambda **kw: _made(900000000000000002))
    guild.create_category = AsyncMock(
        side_effect=lambda *a, **kw: _made(900000000000000001)
    )
    guild.create_text_channel = AsyncMock(
        side_effect=lambda *a, **kw: _made(900000000000000005)
    )
    guild.create_voice_channel = AsyncMock(
        side_effect=lambda *a, **kw: _made(900000000000000006)
    )
    return guild


def test_subscribed_channel_matches_contract() -> None:
    assert _fixture()["channel"] == _CHANNEL


async def test_apply_result_matches_contract_shape() -> None:
    fixture = _fixture()
    result = provisioning.empty_result()
    await provisioning.apply(_guild(), fixture["command"], None, result)

    assert set(result.keys()) == set(fixture["result"].keys()), (
        "provision result keys drifted from fixtures/tilerace_discord.json"
    )
    assert set(result["teams"][0].keys()) == set(fixture["result"]["teams"][0].keys())
    assert result["teams"][0]["team_id"] == fixture["result"]["teams"][0]["team_id"]


async def test_partial_failure_still_reports_what_was_created() -> None:
    """A run that dies mid-way must not leave ids only Discord knows about."""
    import discord

    guild = _guild()
    boom = discord.HTTPException(MagicMock(status=500), "boom")
    guild.create_voice_channel = AsyncMock(side_effect=boom)
    result = provisioning.empty_result()
    with pytest.raises(discord.HTTPException):
        await provisioning.apply(guild, _fixture()["command"], None, result)

    assert result["category_id"] == 900000000000000001
    assert result["captains_role_id"] is not None
    assert result["captains_channel_id"] is not None


async def test_teardown_result_clears_every_id() -> None:
    fixture = _fixture()
    provisioned = dict(fixture["command"])
    provisioned.update(
        category_id="900000000000000001",
        captains_role_id="900000000000000002",
        captains_channel_id="900000000000000003",
        submissions_channel_id="900000000000000007",
    )
    result = await provisioning.teardown(_guild(), provisioned)
    assert result == fixture["teardown_result"]


async def test_result_is_posted_with_the_service_key() -> None:
    from features.tilerace import api_client

    response = MagicMock(status_code=200)
    http = AsyncMock()
    http.post.return_value = response
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=http)
    client.__aexit__ = AsyncMock(return_value=False)

    env = {"API_BACKEND_URL": "http://api", "METRICS_API_KEY": "key"}
    with (
        patch.dict("os.environ", env),
        patch("httpx.AsyncClient", return_value=client),
    ):
        assert await api_client.report_result("12", _fixture()["result"]) is True

    url = http.post.call_args.args[0]
    assert url == "http://api/tilerace/events/12/discord/result"
    assert http.post.call_args.kwargs["headers"] == {"verification-code": "key"}


def _provisioned_guild() -> tuple[MagicMock, dict[int, MagicMock]]:
    """A guild where every object the fixture names already exists."""
    import discord

    guild = _guild()
    channels: dict[int, MagicMock] = {}

    def _channel(oid: int, name: str, cls: type) -> MagicMock:
        obj = MagicMock(spec=cls)
        obj.id = oid
        obj.name = name
        obj.edit = AsyncMock()
        obj.set_permissions = AsyncMock()
        obj.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
        channels[oid] = obj
        return obj

    _channel(900000000000000001, "Summer Tile Race", discord.CategoryChannel)
    _channel(900000000000000003, "captains", discord.TextChannel)
    _channel(900000000000000007, "submissions", discord.TextChannel)
    _channel(900000000000000005, "abyssal-ashes", discord.TextChannel)
    _channel(900000000000000006, "Abyssal Ashes", discord.VoiceChannel)
    role = AsyncMock()
    role.id = 900000000000000004
    role.name = "Abyssal Ashes"
    role.members = []
    captains_role = AsyncMock()
    captains_role.id = 900000000000000002
    captains_role.name = "Summer Tile Race Captains"
    captains_role.members = []

    guild.get_channel = MagicMock(side_effect=lambda oid: channels.get(oid))
    guild.get_role = MagicMock(
        side_effect=lambda oid: {
            900000000000000002: captains_role,
            900000000000000004: role,
        }.get(oid)
    )
    return guild, channels


def _provisioned_command(**permissions: bool) -> dict[str, Any]:
    fixture = _fixture()
    command = dict(fixture["command"])
    command.update(
        action="sync",
        category_id="900000000000000001",
        captains_role_id="900000000000000002",
        captains_channel_id="900000000000000003",
        submissions_channel_id="900000000000000007",
        permissions={
            **dict.fromkeys(fixture["permission_toggles"], False),
            **permissions,
        },
    )
    command["teams"] = [
        {
            **fixture["command"]["teams"][0],
            "role_id": "900000000000000004",
            "text_channel_id": "900000000000000005",
            "voice_channel_id": "900000000000000006",
        }
    ]
    return command


async def test_toggles_reach_existing_channels_without_recreating_them() -> None:
    """A live event must gain the perms in place - no delete, no new channel."""
    guild, channels = _provisioned_guild()
    result = provisioning.empty_result()

    await provisioning.apply(
        guild,
        _provisioned_command(pin_messages=True, mention_everyone=True),
        None,
        result,
    )

    guild.create_text_channel.assert_not_called()
    guild.create_voice_channel.assert_not_called()
    guild.create_category.assert_not_called()
    for channel in channels.values():
        channel.delete.assert_not_called()

    text = channels[900000000000000005]
    overwrite = text.set_permissions.call_args.kwargs["overwrite"]
    assert overwrite.view_channel is True
    assert overwrite.pin_messages is True
    assert overwrite.mention_everyone is True
    assert overwrite.manage_messages is None, (
        "pinning must not hand the team bulk-delete as well"
    )
    assert overwrite.manage_channels is None, "an off toggle must not deny or grant"


async def test_unchanged_channel_costs_no_permission_call() -> None:
    guild, channels = _provisioned_guild()
    from features.tilerace import overwrites

    settled = overwrites.member_grant(perms.text_flags({"pin_messages": True}))
    channels[900000000000000005].overwrites_for = MagicMock(return_value=settled)

    await provisioning.apply(
        guild,
        _provisioned_command(pin_messages=True),
        None,
        provisioning.empty_result(),
    )
    channels[900000000000000005].set_permissions.assert_not_called()


def test_toggles_map_to_the_documented_permissions() -> None:
    assert perms.text_flags({"pin_messages": True}) == {"pin_messages": True}
    assert perms.text_flags({"manage_messages": True}) == {"manage_messages": True}
    assert perms.text_flags({"manage_threads": True}) == {
        "manage_threads": True,
        "create_public_threads": True,
        "send_messages_in_threads": True,
    }
    assert perms.voice_flags({"voice_moderation": True}) == {
        "mute_members": True,
        "deafen_members": True,
        "move_members": True,
    }
    assert perms.text_flags({"voice_moderation": True}) == {}, (
        "a voice-only toggle must not leak onto a text channel"
    )
    assert perms.text_flags(None) == {}


def test_every_contract_toggle_is_wired_to_something() -> None:
    for toggle in _fixture()["permission_toggles"]:
        granted = perms.text_flags({toggle: True}) | perms.voice_flags({toggle: True})
        assert granted, f"{toggle} is in the contract but grants nothing"


def test_channel_names_are_discord_safe() -> None:
    assert (
        naming.channel_name("Zamorak's Chosen (A)", "fallback") == "zamorak-s-chosen-a"
    )
    assert naming.channel_name("", "abyssal-ashes") == "abyssal-ashes"
    assert naming.role_name("Abyssal Ashes") == "Abyssal Ashes"

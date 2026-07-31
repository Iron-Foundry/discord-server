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

from features.tilerace import naming, provisioning
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


def test_channel_names_are_discord_safe() -> None:
    assert (
        naming.channel_name("Zamorak's Chosen (A)", "fallback") == "zamorak-s-chosen-a"
    )
    assert naming.channel_name("", "abyssal-ashes") == "abyssal-ashes"
    assert naming.role_name("Abyssal Ashes") == "Abyssal Ashes"

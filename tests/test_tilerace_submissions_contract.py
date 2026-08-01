"""Guard: the tile race submissions seam matches the shared contract.

discord-server calls api-backend with the service key; api-backend owns the
tables and the claim state machine. Skipped outside the monorepo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from features.tilerace.submissions import api
from features.tilerace.submissions.card import SubmissionCard
from features.tilerace.submissions.layout import card_children

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

pytestmark = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)

_ENV = {"API_BACKEND_URL": "http://api", "METRICS_API_KEY": "key"}


def _fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "tilerace_submission.json").read_text())


def _patched(payload: dict[str, Any], status_code: int = 200) -> tuple[Any, AsyncMock]:
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    http = AsyncMock()
    http.request.return_value = response
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=http)
    client.__aexit__ = AsyncMock(return_value=False)
    return client, http


async def test_context_is_fetched_with_the_service_key() -> None:
    fixture = _fixture()
    client, http = _patched(fixture["context_response"])
    with (
        patch.dict("os.environ", _ENV),
        patch("httpx.AsyncClient", return_value=client),
    ):
        result = await api.get_context(111222333444555666)

    method, url = http.request.call_args.args
    assert method == "GET"
    assert url == "http://api" + fixture["routes"]["context"].split("?")[0].replace(
        "GET ", ""
    )
    assert http.request.call_args.kwargs["headers"] == {fixture["auth_header"]: "key"}
    assert result == fixture["context_response"]


async def test_create_sends_every_field_the_contract_names() -> None:
    fixture = _fixture()
    client, http = _patched(fixture["create_response"])
    request = fixture["create_request"]
    with (
        patch.dict("os.environ", _ENV),
        patch("httpx.AsyncClient", return_value=client),
    ):
        result = await api.create(
            fixture["context_response"]["event_id"],
            int(request["discord_user_id"]),
            request["path_position"],
            request["leaf_keys"],
            request["proof_urls"],
            int(request["discord_thread_id"]),
        )

    method, url = http.request.call_args.args
    assert method == "POST"
    assert url == "http://api/tilerace/events/12/submissions"
    assert http.request.call_args.kwargs["json"] == request
    assert result["tile_status"] in fixture["tile_statuses"]


async def test_review_targets_the_thread_route() -> None:
    fixture = _fixture()
    client, http = _patched(fixture["review_response"])
    request = fixture["review_request"]
    with (
        patch.dict("os.environ", _ENV),
        patch("httpx.AsyncClient", return_value=client),
    ):
        result = await api.review(
            "12",
            int(fixture["create_request"]["discord_thread_id"]),
            request["status"],
            int(request["reviewed_by"]),
            request["review_notes"],
        )

    method, url = http.request.call_args.args
    assert method == "POST"
    assert url == (
        "http://api/tilerace/events/12/submissions/threads/900000000000000008/review"
    )
    assert http.request.call_args.kwargs["json"] == request
    assert result["tile_status"] in fixture["tile_statuses"]


def test_the_card_prints_the_count_and_the_lines_the_api_sends() -> None:
    """An "any one of" tile must not read as three separate obligations.

    The bot counts no leaves of its own: api-backend knows an ``or`` costs one
    submission, and sends both that count and the indented lines to print.
    """
    fixture = _fixture()
    context = {**fixture["context_response"], **fixture["any_of_context_response"]}
    body = "\n".join(
        item.content
        for item in card_children(context, "@Staff")
        if isinstance(item, discord.ui.TextDisplay)
    )

    assert "### Requirements (1 outstanding)" in body
    for line in context["requirement_lines"]:
        assert line in body


def test_the_select_offers_every_branch_of_an_unproved_choice() -> None:
    fixture = _fixture()
    context = {**fixture["context_response"], **fixture["any_of_context_response"]}
    card = SubmissionCard(context, 111222333444555666, "@Staff")

    options = [
        option.value
        for item in card.walk_children()
        if isinstance(item, discord.ui.Select)
        for option in item.options
    ]
    assert options == [leaf["key"] for leaf in context["leaves"]]


def test_a_leaf_the_api_no_longer_needs_is_not_offered() -> None:
    """One branch of an ``or`` landing takes the rest off the menu."""
    fixture = _fixture()
    context = {**fixture["context_response"], **fixture["any_of_context_response"]}
    context["leaves"] = [
        {**leaf, "needed": False, "covered": i == 1}
        for i, leaf in enumerate(context["leaves"])
    ]
    card = SubmissionCard(context, 111222333444555666, "@Staff")

    assert not any(isinstance(item, discord.ui.Select) for item in card.walk_children())


async def test_an_error_response_surfaces_the_api_detail() -> None:
    client, _http = _patched({"detail": "You are not on a team in this event."}, 403)
    with (
        patch.dict("os.environ", _ENV),
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(api.ApiUnavailableError, match="not on a team"),
    ):
        await api.get_context(1)


async def test_missing_credentials_never_reach_the_network() -> None:
    with (
        patch.dict("os.environ", {"API_BACKEND_URL": "", "METRICS_API_KEY": ""}),
        pytest.raises(api.ApiUnavailableError),
    ):
        await api.get_context(1)

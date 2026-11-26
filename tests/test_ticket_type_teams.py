"""Ticket types grant and ping every team they declare."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from features.tickets.models.ticket import TicketTypeConfig
from features.tickets.types import GeneralTicket, JoinCCTicket, RankupTicket

STAFF = 111
SUPPORT = 1441620131678785646

SUPPORT_TYPES = [GeneralTicket, RankupTicket, JoinCCTicket]


def _role(role_id: int) -> MagicMock:
    return MagicMock(id=role_id, mention=f"<@&{role_id}>")


def _guild() -> MagicMock:
    guild = MagicMock()
    guild.roles = [_role(STAFF), _role(SUPPORT)]
    return guild


def _build(cls: type) -> TicketTypeConfig:
    return cls(staff_role_id=STAFF, support_role_id=SUPPORT)


@pytest.mark.parametrize("cls", SUPPORT_TYPES)
def test_support_role_is_a_team(cls: type) -> None:
    assert [t.role_id for t in _build(cls).teams] == [STAFF, SUPPORT]


@pytest.mark.parametrize("cls", SUPPORT_TYPES)
def test_support_role_can_see_the_channel(cls: type) -> None:
    guild = _guild()
    overwrites = _build(cls).get_channel_permissions(guild, MagicMock())
    granted = {
        target.id
        for target, perm in overwrites.items()
        if target in guild.roles and perm.view_channel
    }
    assert granted == {STAFF, SUPPORT}


@pytest.mark.parametrize("cls", SUPPORT_TYPES)
async def test_support_role_is_pinged_on_create(cls: type) -> None:
    channel = MagicMock()
    channel.guild = _guild()
    channel.send = AsyncMock()
    await _build(cls).on_created(MagicMock(), channel)
    channel.send.assert_awaited_once_with(f"<@&{STAFF}> <@&{SUPPORT}>")

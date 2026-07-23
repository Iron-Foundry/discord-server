"""Shared fixtures for discord-server tests.

Mirrors the api-backend async test style: DB access is an AsyncMock session so
tests never touch a real database, and Discord objects are lightweight fakes so
services can be constructed without a live gateway connection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_session() -> MagicMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = 0
    result.scalar_one.return_value = 0
    result.one_or_none.return_value = None
    result.one.return_value = (0, 0)
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.fetchall.return_value = []
    result.rowcount = 0
    session.execute.return_value = result
    session.scalar_one_or_none.return_value = None
    session.scalar.return_value = 0
    session.get.return_value = None
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.delete = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def session_factory(mock_session: MagicMock) -> MagicMock:
    factory = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory


@pytest.fixture
def fake_guild() -> MagicMock:
    guild = MagicMock()
    guild.id = 111222333444555666
    guild.member_count = 42
    guild.members = []
    guild.get_role.return_value = None
    return guild


@pytest.fixture
def fake_client(fake_guild: MagicMock) -> MagicMock:
    client = MagicMock()
    client._guild = fake_guild
    client.get_guild.return_value = fake_guild
    return client

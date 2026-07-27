"""Ticket repository guards that do not need a live database."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from features.tickets.handlers.pg_repository import PgTicketRepository


def _repo() -> PgTicketRepository:
    engine = create_async_engine("postgresql+asyncpg://user:pw@localhost/unused")
    return PgTicketRepository(async_sessionmaker(engine, expire_on_commit=False))


async def test_update_ticket_rejects_unknown_column() -> None:
    with pytest.raises(ValueError, match="Unknown ticket columns"):
        await _repo().update_ticket(1, status="open", not_a_column="x")


async def test_update_ticket_without_fields_is_a_noop() -> None:
    await _repo().update_ticket(1)

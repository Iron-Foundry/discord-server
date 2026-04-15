from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import case, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import Config
from core.db.models import Ticket as OrmTicket
from core.db.models import Transcript as OrmTranscript
from features.tickets.models.stats import HandlerStats, LeaderboardEntry, SystemStats
from features.tickets.models.ticket import MemberSnapshot, TicketRecord, TicketStatus
from features.tickets.models.transcript import Transcript

_PANEL_KEY = "panel"
_TICKET_KEY = "ticket"


class PgTicketRepository:
    """PostgreSQL persistence for the ticket system."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def ensure_indexes(self) -> None:
        """No-op — indexes are managed by Alembic migrations."""
        logger.info("PgTicketRepository: ready")

    # -------------------------------------------------------------------------
    # Counter — auto-increment ticket IDs
    # -------------------------------------------------------------------------

    async def next_ticket_id(self) -> int:
        """Return the next ticket ID from the PG sequence."""
        async with self._factory() as session:
            result = await session.execute(
                text("SELECT nextval('tickets_ticket_id_seq')")
            )
            return result.scalar()

    # -------------------------------------------------------------------------
    # Ticket records
    # -------------------------------------------------------------------------

    async def save_ticket(self, record: TicketRecord) -> None:
        """Upsert a ticket record."""
        row = _record_to_orm_values(record)
        # set_ uses DB column names; extra_metadata maps to the 'metadata' column
        _col_name = {"extra_metadata": "metadata"}
        set_ = {
            _col_name.get(k, k): v
            for k, v in row.items()
            if k != "ticket_id"
        }
        stmt = (
            pg_insert(OrmTicket)
            .values(**row)
            .on_conflict_do_update(index_elements=["ticket_id"], set_=set_)
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def update_ticket(self, ticket_id: int, **fields: Any) -> None:
        """Partially update a ticket. Pass column=value keyword args."""
        if not fields:
            return
        async with self._factory() as session:
            await session.execute(
                text(
                    f"UPDATE tickets SET {', '.join(f'{k} = :{k}' for k in fields)}"
                    f" WHERE ticket_id = :ticket_id"
                ),
                {**fields, "ticket_id": ticket_id},
            )
            await session.commit()

    async def get_ticket(self, ticket_id: int) -> TicketRecord | None:
        """Return a ticket record by ID."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmTicket).where(OrmTicket.ticket_id == ticket_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            try:
                return _orm_to_record(row)
            except Exception as exc:
                logger.error(
                    "PgTicketRepository: failed to hydrate ticket #{}: {}", ticket_id, exc
                )
                return None

    async def get_open_tickets(self, guild_id: int) -> list[TicketRecord]:
        """Return all open tickets for a guild."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmTicket).where(
                    OrmTicket.guild_id == guild_id,
                    OrmTicket.status == TicketStatus.OPEN.value,
                )
            )
            rows = result.scalars().all()
        records: list[TicketRecord] = []
        for row in rows:
            try:
                records.append(_orm_to_record(row))
            except Exception as exc:
                logger.warning(
                    "PgTicketRepository: skipping malformed ticket #{}: {}",
                    row.ticket_id,
                    exc,
                )
        return records

    async def get_recent_closed_tickets(
        self, guild_id: int, limit: int = 25
    ) -> list[TicketRecord]:
        """Return the most recently closed/archived tickets for a guild."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmTicket)
                .where(
                    OrmTicket.guild_id == guild_id,
                    OrmTicket.status.in_(
                        [TicketStatus.CLOSED.value, TicketStatus.ARCHIVED.value]
                    ),
                )
                .order_by(OrmTicket.ticket_id.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
        records: list[TicketRecord] = []
        for row in rows:
            try:
                records.append(_orm_to_record(row))
            except Exception as exc:
                logger.warning(
                    "PgTicketRepository: skipping malformed ticket #{}: {}",
                    row.ticket_id,
                    exc,
                )
        return records

    async def get_tickets_by_user(
        self,
        guild_id: int,
        user_id: int,
        *,
        status: str | None = None,
        limit: int = 25,
    ) -> list[TicketRecord]:
        """Return tickets for a user, newest first. Optionally filter by status."""
        stmt = select(OrmTicket).where(
            OrmTicket.guild_id == guild_id,
            OrmTicket.creator_id == user_id,
        )
        if status is not None:
            stmt = stmt.where(OrmTicket.status == status)
        stmt = stmt.order_by(OrmTicket.ticket_id.desc()).limit(limit)
        async with self._factory() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()
        records: list[TicketRecord] = []
        for row in rows:
            try:
                records.append(_orm_to_record(row))
            except Exception as exc:
                logger.warning(
                    "PgTicketRepository: skipping malformed ticket #{}: {}",
                    row.ticket_id,
                    exc,
                )
        return records

    # -------------------------------------------------------------------------
    # Panel config
    # -------------------------------------------------------------------------

    async def save_panel_config(
        self, guild_id: int, channel_id: int, message_id: int
    ) -> None:
        """Persist the panel channel and message IDs for a guild."""
        value: dict = {"channel_id": channel_id, "message_id": message_id}
        stmt = (
            pg_insert(Config)
            .values(guild_id=guild_id, key=_PANEL_KEY, value=value)
            .on_conflict_do_update(
                index_elements=["guild_id", "key"],
                set_={"value": value},
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def get_panel_config(self, guild_id: int) -> tuple[int, int] | None:
        """Return (channel_id, message_id) for the guild's panel, or None."""
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == guild_id, Config.key == _PANEL_KEY
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return row["channel_id"], row["message_id"]

    async def clear_panel_config(self, guild_id: int) -> None:
        """Remove stale panel config."""
        async with self._factory() as session:
            await session.execute(
                delete(Config).where(
                    Config.guild_id == guild_id, Config.key == _PANEL_KEY
                )
            )
            await session.commit()

    # -------------------------------------------------------------------------
    # Rank details config
    # -------------------------------------------------------------------------

    async def get_rank_details_config(self, guild_id: int) -> dict | None:
        """Return the rank details config document for a guild, or None."""
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == guild_id, Config.key == _TICKET_KEY
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            data = dict(row)
            data["guild_id"] = guild_id
            # Decode base64-encoded image data back to bytes
            for field_key in ("rank_reqs_data", "rank_upgrades_data"):
                if field_key in data and isinstance(data[field_key], str):
                    data[field_key] = base64.b64decode(data[field_key])
            return data

    async def set_rank_details_image(
        self, guild_id: int, key: str, filename: str, data: bytes
    ) -> None:
        """Upsert a rank image (rank_reqs or rank_upgrades) for a guild."""
        new_fields = {
            f"{key}_filename": filename,
            f"{key}_data": base64.b64encode(data).decode(),
        }
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == guild_id, Config.key == _TICKET_KEY
                )
            )
            existing = result.scalar_one_or_none() or {}
            merged = {**existing, **new_fields}
            stmt = (
                pg_insert(Config)
                .values(guild_id=guild_id, key=_TICKET_KEY, value=merged)
                .on_conflict_do_update(
                    index_elements=["guild_id", "key"],
                    set_={"value": merged},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def set_rank_details_join_text(self, guild_id: int, join_text: str) -> None:
        """Upsert the join ticket welcome text for a guild."""
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == guild_id, Config.key == _TICKET_KEY
                )
            )
            existing = result.scalar_one_or_none() or {}
            merged = {**existing, "join_text": join_text}
            stmt = (
                pg_insert(Config)
                .values(guild_id=guild_id, key=_TICKET_KEY, value=merged)
                .on_conflict_do_update(
                    index_elements=["guild_id", "key"],
                    set_={"value": merged},
                )
            )
            await session.execute(stmt)
            await session.commit()

    # -------------------------------------------------------------------------
    # Transcripts
    # -------------------------------------------------------------------------

    async def save_transcript(self, transcript: Transcript) -> bool:
        """Upsert a ticket transcript.

        The full Transcript model dump is stored in the ``entries`` JSONB column
        so that all metadata (channel_id, guild_id, etc.) round-trips correctly.
        """
        full_dump = transcript.model_dump(mode="json")
        stmt = (
            pg_insert(OrmTranscript)
            .values(ticket_id=transcript.ticket_id, entries=full_dump)
            .on_conflict_do_update(
                index_elements=["ticket_id"],
                set_={"entries": full_dump},
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()
        return True

    async def get_transcript(self, ticket_id: int) -> Transcript | None:
        """Return a transcript by ticket ID."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmTranscript).where(OrmTranscript.ticket_id == ticket_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            try:
                return Transcript.model_validate(row.entries)
            except Exception as exc:
                logger.error(
                    "PgTicketRepository: failed to hydrate transcript #{}: {}",
                    ticket_id,
                    exc,
                )
                return None

    # -------------------------------------------------------------------------
    # Stats aggregations
    # -------------------------------------------------------------------------

    async def get_handler_stats(
        self,
        guild_id: int,
        staff_id: int,
        since: datetime | None = None,
    ) -> HandlerStats | None:
        """Return aggregated stats for a single staff handler."""
        closed_statuses = [TicketStatus.CLOSED.value, TicketStatus.ARCHIVED.value]

        # Base filter for closed tickets by this staff member
        closed_where = [
            OrmTicket.guild_id == guild_id,
            OrmTicket.status.in_(closed_statuses),
            OrmTicket.closed_by_id == staff_id,
        ]
        if since is not None:
            closed_where.append(OrmTicket.created_at >= since)

        participated_where = [
            OrmTicket.guild_id == guild_id,
            OrmTicket.participants.any(staff_id),
        ]
        if since is not None:
            participated_where.append(OrmTicket.created_at >= since)

        resolution_secs = func.extract(
            "epoch", OrmTicket.closed_at - OrmTicket.created_at
        )
        response_secs = func.extract(
            "epoch", OrmTicket.first_staff_response_at - OrmTicket.created_at
        )

        async with self._factory() as session:
            tickets_participated, agg_result, breakdown_result = await asyncio.gather(
                session.execute(
                    select(func.count()).select_from(OrmTicket).where(*participated_where)
                ),
                session.execute(
                    select(
                        func.count().label("tickets_closed"),
                        func.avg(
                            case(
                                (
                                    OrmTicket.closed_at.is_not(None)
                                    & OrmTicket.created_at.is_not(None),
                                    resolution_secs,
                                ),
                                else_=None,
                            )
                        ).label("avg_resolution_seconds"),
                        func.avg(
                            case(
                                (
                                    OrmTicket.first_staff_response_at.is_not(None)
                                    & OrmTicket.created_at.is_not(None),
                                    response_secs,
                                ),
                                else_=None,
                            )
                        ).label("avg_response_seconds"),
                    ).where(*closed_where)
                ),
                session.execute(
                    select(OrmTicket.ticket_type, func.count().label("cnt"))
                    .where(*closed_where)
                    .group_by(OrmTicket.ticket_type)
                ),
            )

        participated_count = tickets_participated.scalar() or 0
        agg = agg_result.one()
        if not agg.tickets_closed:
            return None

        type_breakdown = {row.ticket_type: row.cnt for row in breakdown_result.all()}

        return HandlerStats(
            staff_id=staff_id,
            tickets_closed=agg.tickets_closed,
            tickets_participated=participated_count,
            avg_response_seconds=float(agg.avg_response_seconds)
            if agg.avg_response_seconds is not None
            else None,
            avg_resolution_seconds=float(agg.avg_resolution_seconds)
            if agg.avg_resolution_seconds is not None
            else None,
            type_breakdown=type_breakdown,
        )

    async def get_leaderboard_stats(
        self,
        guild_id: int,
        since: datetime | None = None,
        limit: int = 10,
        exclude_ids: list[int] | None = None,
        metric: str = "closed",
    ) -> list[LeaderboardEntry]:
        """Return top handlers ranked by the given metric."""
        if metric == "participated":
            return await self._get_participated_leaderboard(
                guild_id, since, limit, exclude_ids
            )

        closed_statuses = [TicketStatus.CLOSED.value, TicketStatus.ARCHIVED.value]
        where = [
            OrmTicket.guild_id == guild_id,
            OrmTicket.status.in_(closed_statuses),
            OrmTicket.closed_by_id.is_not(None),
        ]
        if since is not None:
            where.append(OrmTicket.created_at >= since)
        if exclude_ids:
            where.append(OrmTicket.closed_by_id.not_in(exclude_ids))

        resolution_secs = func.extract(
            "epoch", OrmTicket.closed_at - OrmTicket.created_at
        )
        stmt = (
            select(
                OrmTicket.closed_by_id.label("staff_id"),
                func.count().label("tickets_closed"),
                func.avg(
                    case(
                        (
                            OrmTicket.closed_at.is_not(None)
                            & OrmTicket.created_at.is_not(None),
                            resolution_secs,
                        ),
                        else_=None,
                    )
                ).label("avg_resolution_seconds"),
            )
            .where(*where)
            .group_by(OrmTicket.closed_by_id)
            .order_by(func.count().desc())
            .limit(limit)
        )

        async with self._factory() as session:
            result = await session.execute(stmt)
            rows = result.all()

        return [
            LeaderboardEntry(
                rank=rank,
                staff_id=row.staff_id,
                tickets_closed=row.tickets_closed,
                avg_resolution_seconds=float(row.avg_resolution_seconds)
                if row.avg_resolution_seconds is not None
                else None,
            )
            for rank, row in enumerate(rows, start=1)
        ]

    async def _get_participated_leaderboard(
        self,
        guild_id: int,
        since: datetime | None,
        limit: int,
        exclude_ids: list[int] | None,
    ) -> list[LeaderboardEntry]:
        """Return top handlers ranked by tickets participated in."""
        where_clause = "WHERE t.guild_id = :guild_id"
        params: dict = {"guild_id": guild_id, "limit": limit}
        if since is not None:
            where_clause += " AND t.created_at >= :since"
            params["since"] = since

        exclude_clause = ""
        if exclude_ids:
            placeholders = ", ".join(f":exc_{i}" for i in range(len(exclude_ids)))
            exclude_clause = f"AND p.staff_id NOT IN ({placeholders})"
            for i, eid in enumerate(exclude_ids):
                params[f"exc_{i}"] = eid

        sql = text(
            f"SELECT p.staff_id, COUNT(*) AS cnt"
            f" FROM tickets t"
            f" JOIN LATERAL unnest(t.participants) AS p(staff_id) ON TRUE"
            f" {where_clause}"
            f" {exclude_clause}"
            f" GROUP BY p.staff_id"
            f" ORDER BY cnt DESC"
            f" LIMIT :limit"
        )

        async with self._factory() as session:
            result = await session.execute(sql, params)
            rows = result.all()

        return [
            LeaderboardEntry(
                rank=rank,
                staff_id=row.staff_id,
                tickets_closed=0,
                avg_resolution_seconds=None,
                tickets_participated=row.cnt,
            )
            for rank, row in enumerate(rows, start=1)
        ]

    async def get_system_stats(
        self,
        guild_id: int,
        since: datetime | None = None,
    ) -> SystemStats:
        """Return aggregated system-wide ticket statistics for the guild."""
        closed_statuses = [TicketStatus.CLOSED.value, TicketStatus.ARCHIVED.value]

        where_all = [OrmTicket.guild_id == guild_id]
        if since is not None:
            where_all.append(OrmTicket.created_at >= since)

        where_closed = [
            OrmTicket.guild_id == guild_id,
            OrmTicket.status.in_(closed_statuses),
        ]
        if since is not None:
            where_closed.append(OrmTicket.created_at >= since)

        resolution_secs = func.extract(
            "epoch", OrmTicket.closed_at - OrmTicket.created_at
        )
        response_secs = func.extract(
            "epoch", OrmTicket.first_staff_response_at - OrmTicket.created_at
        )

        async with self._factory() as session:
            currently_open_res, total_opened_res, closed_agg_res, breakdown_res = (
                await asyncio.gather(
                    session.execute(
                        select(func.count()).select_from(OrmTicket).where(
                            OrmTicket.guild_id == guild_id,
                            OrmTicket.status == TicketStatus.OPEN.value,
                        )
                    ),
                    session.execute(
                        select(func.count()).select_from(OrmTicket).where(*where_all)
                    ),
                    session.execute(
                        select(
                            func.count().label("total_closed"),
                            func.avg(
                                case(
                                    (
                                        OrmTicket.closed_at.is_not(None)
                                        & OrmTicket.created_at.is_not(None),
                                        resolution_secs,
                                    ),
                                    else_=None,
                                )
                            ).label("avg_resolution_seconds"),
                            func.avg(
                                case(
                                    (
                                        OrmTicket.first_staff_response_at.is_not(None)
                                        & OrmTicket.created_at.is_not(None),
                                        response_secs,
                                    ),
                                    else_=None,
                                )
                            ).label("avg_response_seconds"),
                        ).where(*where_closed)
                    ),
                    session.execute(
                        select(OrmTicket.ticket_type, func.count().label("cnt"))
                        .where(*where_all)
                        .group_by(OrmTicket.ticket_type)
                    ),
                )
            )

        currently_open = currently_open_res.scalar() or 0
        total_opened = total_opened_res.scalar() or 0
        closed_agg = closed_agg_res.one()
        type_breakdown = {
            row.ticket_type: row.cnt for row in breakdown_res.all()
        }

        return SystemStats(
            total_opened=total_opened,
            total_closed=closed_agg.total_closed or 0,
            currently_open=currently_open,
            avg_response_seconds=float(closed_agg.avg_response_seconds)
            if closed_agg.avg_response_seconds is not None
            else None,
            avg_resolution_seconds=float(closed_agg.avg_resolution_seconds)
            if closed_agg.avg_resolution_seconds is not None
            else None,
            type_breakdown=type_breakdown,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record_to_orm_values(record: TicketRecord) -> dict:
    """Convert a TicketRecord to a dict suitable for ORM insertion."""
    meta = dict(record.metadata)
    meta["_creator"] = record.creator.model_dump(mode="json")

    return {
        "ticket_id": record.ticket_id,
        "guild_id": record.guild_id,
        "ticket_type": record.ticket_type,
        "status": record.status.value,
        "created_at": record.created_at,
        "closed_at": record.closed_at,
        "last_message_at": record.last_message_at,
        "channel_id": record.channel_id,
        "creator_id": record.creator.id,
        "creator_name": record.creator.name,
        "assigned_staff": record.assigned_staff,
        "participants": record.participants,
        "closed_by_id": record.closed_by_id,
        "first_staff_response_at": record.first_staff_response_at,
        "panel_message_id": record.panel_message_id,
        "staff_note": record.staff_note,
        "close_reason": record.close_reason,
        "reopen_history": [e.model_dump(mode="json") for e in record.reopen_history],
        "timeout_frozen": record.timeout_frozen,
        "extra_metadata": meta,
    }


def _orm_to_record(row: OrmTicket) -> TicketRecord:
    """Reconstruct a TicketRecord from an ORM Ticket row."""
    from features.tickets.models.ticket import ReopenEvent

    meta: dict = dict(row.extra_metadata or {})
    creator_data: dict | None = meta.pop("_creator", None)

    if creator_data:
        creator = MemberSnapshot.model_validate(creator_data)
    else:
        creator = MemberSnapshot(
            id=row.creator_id,
            name=row.creator_name,
            display_name=row.creator_name,
            avatar_url="",
        )

    reopen_history = [
        ReopenEvent.model_validate(e) for e in (row.reopen_history or [])
    ]

    return TicketRecord(
        ticket_id=row.ticket_id,
        guild_id=row.guild_id,
        channel_id=row.channel_id or 0,
        panel_message_id=row.panel_message_id,
        creator=creator,
        ticket_type=row.ticket_type,
        status=TicketStatus(row.status),
        timeout_frozen=row.timeout_frozen,
        last_message_at=row.last_message_at or row.created_at,
        created_at=row.created_at,
        closed_at=row.closed_at,
        closed_by_id=row.closed_by_id,
        close_reason=row.close_reason,
        staff_note=row.staff_note,
        first_staff_response_at=row.first_staff_response_at,
        participants=list(row.participants or []),
        assigned_staff=list(row.assigned_staff or []),
        reopen_history=reopen_history,
        metadata=meta,
    )

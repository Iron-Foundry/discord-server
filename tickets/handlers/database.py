import asyncio
from datetime import datetime

from loguru import logger
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from tickets.models.stats import HandlerStats, LeaderboardEntry, SystemStats
from tickets.models.ticket import TicketRecord, TicketStatus
from tickets.models.transcript import Transcript


class MongoTicketRepository:
    """
    Handles all MongoDB persistence for the ticket system.

    Collections:
      - tickets:     one document per ticket (TicketRecord)
      - transcripts: one document per ticket (Transcript)
      - counters:    {_id: "ticket_id", seq: int} for auto-increment IDs
    """

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(mongo_uri)
        self._db = self._client[db_name]
        self._tickets = self._db["tickets"]
        self._transcripts = self._db["transcripts"]
        self._counters = self._db["counters"]
        self._panel_config = self._db["panel_config"]
        self._ticket_config = self._db["ticket_config"]

    async def ensure_indexes(self) -> None:
        """Create indexes on startup. Safe to call multiple times."""
        await self._tickets.create_index([("ticket_id", ASCENDING)], unique=True)
        await self._tickets.create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)]
        )
        await self._tickets.create_index([("channel_id", ASCENDING)])
        await self._tickets.create_index(
            [("guild_id", ASCENDING), ("creator.id", ASCENDING)]
        )
        await self._transcripts.create_index([("ticket_id", ASCENDING)], unique=True)
        logger.info("MongoTicketRepository: indexes ensured")

    # -------------------------------------------------------------------------
    # Counter — auto-increment ticket IDs
    # -------------------------------------------------------------------------

    async def next_ticket_id(self) -> int:
        """Atomically increment and return the next ticket ID."""
        result = await self._counters.find_one_and_update(
            {"_id": "ticket_id"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        return result["seq"]

    # -------------------------------------------------------------------------
    # Ticket records
    # -------------------------------------------------------------------------

    async def save_ticket(self, record: TicketRecord) -> None:
        try:
            doc = record.model_dump(mode="json")
            await self._tickets.replace_one(
                {"ticket_id": record.ticket_id}, doc, upsert=True
            )
        except PyMongoError as e:
            logger.error(f"Failed to save ticket #{record.ticket_id}: {e}")

    async def update_ticket(self, ticket_id: int, **fields) -> None:
        """Partially update a ticket document. Pass field=value keyword args."""
        try:
            await self._tickets.update_one({"ticket_id": ticket_id}, {"$set": fields})
        except PyMongoError as e:
            logger.error(f"Failed to update ticket #{ticket_id}: {e}")

    async def get_ticket(self, ticket_id: int) -> TicketRecord | None:
        try:
            doc = await self._tickets.find_one({"ticket_id": ticket_id}, {"_id": 0})
            return TicketRecord.model_validate(doc) if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to fetch ticket #{ticket_id}: {e}")
            return None

    async def get_open_tickets(self, guild_id: int) -> list[TicketRecord]:
        """Return all OPEN tickets for a guild (used for restart recovery)."""
        try:
            cursor = self._tickets.find(
                {"guild_id": guild_id, "status": TicketStatus.OPEN.value}, {"_id": 0}
            )
            records: list[TicketRecord] = []
            async for doc in cursor:
                try:
                    records.append(TicketRecord.model_validate(doc))
                except Exception as e:
                    logger.warning(f"Skipping malformed ticket document: {e}")
            return records
        except PyMongoError as e:
            logger.error(f"Failed to fetch open tickets for guild {guild_id}: {e}")
            return []

    # -------------------------------------------------------------------------
    # Panel config
    # -------------------------------------------------------------------------

    async def save_panel_config(
        self, guild_id: int, channel_id: int, message_id: int
    ) -> None:
        """Persist the panel channel and message IDs for a guild."""
        try:
            await self._panel_config.replace_one(
                {"guild_id": guild_id},
                {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                },
                upsert=True,
            )
        except PyMongoError as e:
            logger.error(f"Failed to save panel config for guild {guild_id}: {e}")

    async def get_panel_config(self, guild_id: int) -> tuple[int, int] | None:
        """Return (channel_id, message_id) for the guild's panel, or None."""
        try:
            doc = await self._panel_config.find_one({"guild_id": guild_id}, {"_id": 0})
            if doc:
                return doc["channel_id"], doc["message_id"]
            return None
        except PyMongoError as e:
            logger.error(f"Failed to fetch panel config for guild {guild_id}: {e}")
            return None

    async def clear_panel_config(self, guild_id: int) -> None:
        """Remove stale panel config (e.g. message was deleted)."""
        try:
            await self._panel_config.delete_one({"guild_id": guild_id})
        except PyMongoError as e:
            logger.error(f"Failed to clear panel config for guild {guild_id}: {e}")

    # -------------------------------------------------------------------------
    # Rank details config
    # -------------------------------------------------------------------------

    async def get_rank_details_config(self, guild_id: int) -> dict | None:
        """Return the rank details config document for a guild, or None."""
        try:
            return await self._ticket_config.find_one(
                {"guild_id": guild_id}, {"_id": 0}
            )
        except PyMongoError as e:
            logger.error(
                f"Failed to fetch rank details config for guild {guild_id}: {e}"
            )
            return None

    async def set_rank_details_image(
        self, guild_id: int, key: str, filename: str, data: bytes
    ) -> None:
        """Upsert a rank image (rank_reqs or rank_upgrades) for a guild."""
        try:
            await self._ticket_config.update_one(
                {"guild_id": guild_id},
                {
                    "$set": {
                        "guild_id": guild_id,
                        f"{key}_filename": filename,
                        f"{key}_data": data,
                    }
                },
                upsert=True,
            )
        except PyMongoError as e:
            logger.error(f"Failed to set rank image '{key}' for guild {guild_id}: {e}")

    async def set_rank_details_join_text(self, guild_id: int, text: str) -> None:
        """Upsert the join ticket welcome text for a guild."""
        try:
            await self._ticket_config.update_one(
                {"guild_id": guild_id},
                {"$set": {"guild_id": guild_id, "join_text": text}},
                upsert=True,
            )
        except PyMongoError as e:
            logger.error(f"Failed to set join text for guild {guild_id}: {e}")

    async def get_tickets_by_user(
        self,
        guild_id: int,
        user_id: int,
        *,
        status: str | None = None,
        limit: int = 25,
    ) -> list[TicketRecord]:
        """Return tickets for a user, newest first. Optionally filter by status."""
        query: dict = {"guild_id": guild_id, "creator.id": user_id}
        if status is not None:
            query["status"] = status
        try:
            cursor = (
                self._tickets.find(query, {"_id": 0})
                .sort("ticket_id", DESCENDING)
                .limit(limit)
            )
            records: list[TicketRecord] = []
            async for doc in cursor:
                try:
                    records.append(TicketRecord.model_validate(doc))
                except Exception as e:
                    logger.warning(f"Skipping malformed ticket document: {e}")
            return records
        except PyMongoError as e:
            logger.error(f"Failed to fetch tickets for user {user_id}: {e}")
            return []

    # -------------------------------------------------------------------------
    # Transcripts
    # -------------------------------------------------------------------------

    async def save_transcript(self, transcript: Transcript) -> bool:
        try:
            doc = transcript.model_dump(mode="json")
            await self._transcripts.replace_one(
                {"ticket_id": transcript.ticket_id}, doc, upsert=True
            )
            return True
        except PyMongoError as e:
            logger.error(
                f"Failed to save transcript for ticket #{transcript.ticket_id}: {e}"
            )
            return False

    async def get_transcript(self, ticket_id: int) -> Transcript | None:
        try:
            doc = await self._transcripts.find_one({"ticket_id": ticket_id}, {"_id": 0})
            return Transcript.model_validate(doc) if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to fetch transcript for ticket #{ticket_id}: {e}")
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
        match: dict = {
            "guild_id": guild_id,
            "status": {"$in": [TicketStatus.CLOSED.value, TicketStatus.ARCHIVED.value]},
            "closed_by_id": staff_id,
        }
        if since is not None:
            match["created_at"] = {"$gte": since.isoformat()}

        pipeline = [
            {"$match": match},
            {
                "$facet": {
                    "totals": [
                        {
                            "$group": {
                                "_id": None,
                                "tickets_closed": {"$sum": 1},
                                "avg_resolution_ms": {
                                    "$avg": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {"$ne": ["$closed_at", None]},
                                                    {"$ne": ["$created_at", None]},
                                                ]
                                            },
                                            {
                                                "$subtract": [
                                                    {"$toDate": "$closed_at"},
                                                    {"$toDate": "$created_at"},
                                                ]
                                            },
                                            None,
                                        ]
                                    }
                                },
                                "avg_response_ms": {
                                    "$avg": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {
                                                        "$ne": [
                                                            "$first_staff_response_at",
                                                            None,
                                                        ]
                                                    },
                                                    {"$ne": ["$created_at", None]},
                                                ]
                                            },
                                            {
                                                "$subtract": [
                                                    {
                                                        "$toDate": "$first_staff_response_at"
                                                    },
                                                    {"$toDate": "$created_at"},
                                                ]
                                            },
                                            None,
                                        ]
                                    }
                                },
                            }
                        }
                    ],
                    "type_breakdown": [
                        {"$group": {"_id": "$ticket_type", "count": {"$sum": 1}}}
                    ],
                }
            },
        ]

        try:
            participated_match: dict = {
                "guild_id": guild_id,
                "participants": staff_id,
            }
            if since is not None:
                participated_match["created_at"] = {"$gte": since.isoformat()}

            tickets_participated, cursor = await asyncio.gather(
                self._tickets.count_documents(participated_match),
                self._tickets.aggregate(pipeline),
            )
            result = await cursor.to_list(length=1)
            if not result:
                return None

            facet = result[0]
            totals_list: list[dict] = facet.get("totals", [])
            if not totals_list or totals_list[0].get("tickets_closed", 0) == 0:
                return None

            totals = totals_list[0]
            type_breakdown = {
                doc["_id"]: doc["count"]
                for doc in facet.get("type_breakdown", [])
                if doc.get("_id") is not None
            }

            avg_res_ms = totals.get("avg_resolution_ms")
            avg_resp_ms = totals.get("avg_response_ms")

            return HandlerStats(
                staff_id=staff_id,
                tickets_closed=totals["tickets_closed"],
                tickets_participated=tickets_participated,
                avg_response_seconds=avg_resp_ms / 1000 if avg_resp_ms else None,
                avg_resolution_seconds=avg_res_ms / 1000 if avg_res_ms else None,
                type_breakdown=type_breakdown,
            )
        except PyMongoError as e:
            logger.error(f"get_handler_stats failed for staff {staff_id}: {e}")
            return None

    async def get_leaderboard_stats(
        self,
        guild_id: int,
        since: datetime | None = None,
        limit: int = 10,
        exclude_ids: list[int] | None = None,
        metric: str = "closed",
    ) -> list[LeaderboardEntry]:
        """Return top handlers ranked by the given metric.

        Args:
            metric: ``"closed"`` ranks by tickets closed; ``"resolution"`` by avg
                resolution time; ``"participated"`` by tickets participated in.
        """
        if metric == "participated":
            return await self._get_participated_leaderboard(
                guild_id, since, limit, exclude_ids
            )

        match: dict = {
            "guild_id": guild_id,
            "status": {"$in": [TicketStatus.CLOSED.value, TicketStatus.ARCHIVED.value]},
            "closed_by_id": {
                "$nin": exclude_ids or [],
                "$ne": None,
            },
        }
        if since is not None:
            match["created_at"] = {"$gte": since.isoformat()}

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": "$closed_by_id",
                    "tickets_closed": {"$sum": 1},
                    "avg_resolution_ms": {
                        "$avg": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$ne": ["$closed_at", None]},
                                        {"$ne": ["$created_at", None]},
                                    ]
                                },
                                {
                                    "$subtract": [
                                        {"$toDate": "$closed_at"},
                                        {"$toDate": "$created_at"},
                                    ]
                                },
                                None,
                            ]
                        }
                    },
                }
            },
            {"$sort": {"tickets_closed": DESCENDING}},
            {"$limit": limit},
        ]

        try:
            cursor = await self._tickets.aggregate(pipeline)
            docs = await cursor.to_list(length=limit)
            entries: list[LeaderboardEntry] = []
            for rank, doc in enumerate(docs, start=1):
                avg_ms = doc.get("avg_resolution_ms")
                entries.append(
                    LeaderboardEntry(
                        rank=rank,
                        staff_id=doc["_id"],
                        tickets_closed=doc["tickets_closed"],
                        avg_resolution_seconds=avg_ms / 1000 if avg_ms else None,
                    )
                )
            return entries
        except PyMongoError as e:
            logger.error(f"get_leaderboard_stats failed for guild {guild_id}: {e}")
            return []

    async def _get_participated_leaderboard(
        self,
        guild_id: int,
        since: datetime | None,
        limit: int,
        exclude_ids: list[int] | None,
    ) -> list[LeaderboardEntry]:
        """Return top handlers ranked by tickets participated in."""
        match: dict = {"guild_id": guild_id}
        if since is not None:
            match["created_at"] = {"$gte": since.isoformat()}

        pipeline = [
            {"$match": match},
            {"$unwind": "$participants"},
            {"$match": {"participants": {"$nin": exclude_ids or []}}},
            {"$group": {"_id": "$participants", "tickets_participated": {"$sum": 1}}},
            {"$sort": {"tickets_participated": DESCENDING}},
            {"$limit": limit},
        ]

        try:
            cursor = await self._tickets.aggregate(pipeline)
            docs = await cursor.to_list(length=limit)
            return [
                LeaderboardEntry(
                    rank=rank,
                    staff_id=doc["_id"],
                    tickets_closed=0,
                    avg_resolution_seconds=None,
                    tickets_participated=doc["tickets_participated"],
                )
                for rank, doc in enumerate(docs, start=1)
            ]
        except PyMongoError as e:
            logger.error(
                f"_get_participated_leaderboard failed for guild {guild_id}: {e}"
            )
            return []

    async def get_system_stats(
        self,
        guild_id: int,
        since: datetime | None = None,
    ) -> SystemStats:
        """Return aggregated system-wide ticket statistics for the guild."""
        match: dict = {"guild_id": guild_id}
        if since is not None:
            match["created_at"] = {"$gte": since.isoformat()}

        pipeline = [
            {"$match": match},
            {
                "$facet": {
                    "opened": [{"$count": "total"}],
                    "closed": [
                        {
                            "$match": {
                                "status": {
                                    "$in": [
                                        TicketStatus.CLOSED.value,
                                        TicketStatus.ARCHIVED.value,
                                    ]
                                }
                            }
                        },
                        {
                            "$group": {
                                "_id": None,
                                "total": {"$sum": 1},
                                "avg_resolution_ms": {
                                    "$avg": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {"$ne": ["$closed_at", None]},
                                                    {"$ne": ["$created_at", None]},
                                                ]
                                            },
                                            {
                                                "$subtract": [
                                                    {"$toDate": "$closed_at"},
                                                    {"$toDate": "$created_at"},
                                                ]
                                            },
                                            None,
                                        ]
                                    }
                                },
                                "avg_response_ms": {
                                    "$avg": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {
                                                        "$ne": [
                                                            "$first_staff_response_at",
                                                            None,
                                                        ]
                                                    },
                                                    {"$ne": ["$created_at", None]},
                                                ]
                                            },
                                            {
                                                "$subtract": [
                                                    {
                                                        "$toDate": "$first_staff_response_at"
                                                    },
                                                    {"$toDate": "$created_at"},
                                                ]
                                            },
                                            None,
                                        ]
                                    }
                                },
                            }
                        },
                    ],
                    "type_breakdown": [
                        {"$group": {"_id": "$ticket_type", "count": {"$sum": 1}}}
                    ],
                }
            },
        ]

        try:
            currently_open = await self._tickets.count_documents(
                {"guild_id": guild_id, "status": TicketStatus.OPEN.value}
            )
            cursor = await self._tickets.aggregate(pipeline)
            result = await cursor.to_list(length=1)

            if not result:
                return SystemStats(
                    total_opened=0,
                    total_closed=0,
                    currently_open=currently_open,
                    avg_response_seconds=None,
                    avg_resolution_seconds=None,
                    type_breakdown={},
                )

            facet = result[0]
            opened_list: list[dict] = facet.get("opened", [])
            total_opened = opened_list[0]["total"] if opened_list else 0

            closed_list: list[dict] = facet.get("closed", [])
            if closed_list:
                closed_data = closed_list[0]
                total_closed = closed_data.get("total", 0)
                avg_res_ms = closed_data.get("avg_resolution_ms")
                avg_resp_ms = closed_data.get("avg_response_ms")
            else:
                total_closed = 0
                avg_res_ms = None
                avg_resp_ms = None

            type_breakdown = {
                doc["_id"]: doc["count"]
                for doc in facet.get("type_breakdown", [])
                if doc.get("_id") is not None
            }

            return SystemStats(
                total_opened=total_opened,
                total_closed=total_closed,
                currently_open=currently_open,
                avg_response_seconds=avg_resp_ms / 1000 if avg_resp_ms else None,
                avg_resolution_seconds=avg_res_ms / 1000 if avg_res_ms else None,
                type_breakdown=type_breakdown,
            )
        except PyMongoError as e:
            logger.error(f"get_system_stats failed for guild {guild_id}: {e}")
            return SystemStats(
                total_opened=0,
                total_closed=0,
                currently_open=0,
                avg_response_seconds=None,
                avg_resolution_seconds=None,
                type_breakdown={},
            )

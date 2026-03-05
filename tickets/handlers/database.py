from loguru import logger
from pymongo import AsyncMongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

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

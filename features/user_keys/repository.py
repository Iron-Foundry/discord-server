from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from features.user_keys.models import UserKey


class MongoUserKeyRepository:
    """MongoDB persistence for per-user API keys."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(mongo_uri)
        self._db = self._client[db_name]
        self._keys = self._db["user_keys"]

    async def ensure_indexes(self) -> None:
        """Create indexes on startup. Safe to call multiple times."""
        await self._keys.create_index([("discord_user_id", ASCENDING)], unique=True)
        await self._keys.create_index([("key", ASCENDING)], unique=True)
        logger.info("MongoUserKeyRepository: indexes ensured")

    async def get_by_user(self, discord_user_id: int) -> UserKey | None:
        """Return the active key for a user, or None if they have none."""
        try:
            doc = await self._keys.find_one(
                {"discord_user_id": discord_user_id, "is_active": True},
                {"_id": 0},
            )
            return UserKey.model_validate(doc) if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to fetch key for user {discord_user_id}: {e}")
            return None

    async def save(self, user_key: UserKey) -> None:
        """Upsert a user key, replacing any existing key for that user."""
        try:
            doc = user_key.model_dump(mode="json")
            await self._keys.replace_one(
                {"discord_user_id": user_key.discord_user_id}, doc, upsert=True
            )
        except PyMongoError as e:
            logger.error(f"Failed to save key for user {user_key.discord_user_id}: {e}")

    async def upsert_user_profile(self, user_key: UserKey) -> None:
        """Create or refresh the unified user profile for this user key."""
        now = datetime.now(timezone.utc)
        try:
            await self._db["users"].update_one(
                {"discord_user_id": user_key.discord_user_id},
                {
                    "$setOnInsert": {
                        "discord_user_id": user_key.discord_user_id,
                        "rsn": None,
                        "clan_rank": None,
                        "ticket_ids": [],
                        "created_at": now,
                    },
                    "$set": {
                        "discord_username": user_key.discord_username,
                        "guild_id": user_key.guild_id,
                        "guild_name": user_key.guild_name,
                        "updated_at": now,
                    },
                },
                upsert=True,
            )
        except PyMongoError as e:
            logger.error(
                f"Failed to upsert user profile for {user_key.discord_user_id}: {e}"
            )

    async def get_user_profile(self, discord_user_id: int) -> dict | None:
        """Return the unified user profile doc, or None if not found."""
        try:
            return await self._db["users"].find_one(
                {"discord_user_id": discord_user_id}, {"_id": 0}
            )
        except PyMongoError as e:
            logger.error(f"Failed to fetch user profile for {discord_user_id}: {e}")
            return None

    async def link_rsn(self, discord_user_id: int, rsn: str) -> None:
        """Set the RSN on a user profile, creating the doc if it does not exist."""
        now = datetime.now(timezone.utc)
        try:
            await self._db["users"].update_one(
                {"discord_user_id": discord_user_id},
                {
                    "$setOnInsert": {
                        "discord_user_id": discord_user_id,
                        "discord_username": "",
                        "guild_id": 0,
                        "guild_name": "",
                        "clan_rank": None,
                        "ticket_ids": [],
                        "stats_opt_out": False,
                        "created_at": now,
                    },
                    "$set": {"rsn": rsn, "updated_at": now},
                },
                upsert=True,
            )
        except PyMongoError as e:
            logger.error(f"Failed to link RSN for {discord_user_id}: {e}")

    async def set_stats_opt_out(self, discord_user_id: int, opt_out: bool) -> None:
        """Set or clear the stats opt-out flag on a user profile.

        Upserts a minimal doc if the user has no profile yet.
        """
        now = datetime.now(timezone.utc)
        try:
            await self._db["users"].update_one(
                {"discord_user_id": discord_user_id},
                {
                    "$setOnInsert": {
                        "discord_user_id": discord_user_id,
                        "discord_username": "",
                        "guild_id": 0,
                        "guild_name": "",
                        "rsn": None,
                        "clan_rank": None,
                        "ticket_ids": [],
                        "created_at": now,
                    },
                    "$set": {"stats_opt_out": opt_out, "updated_at": now},
                },
                upsert=True,
            )
        except PyMongoError as e:
            logger.error(
                f"Failed to set stats_opt_out for {discord_user_id}: {e}"
            )

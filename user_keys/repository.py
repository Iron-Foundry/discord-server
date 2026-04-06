from __future__ import annotations

from loguru import logger
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from user_keys.models import UserKey


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

from __future__ import annotations

from loguru import logger
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from action_log.models import ActionLogConfig


class MongoActionLogRepository:
    """MongoDB persistence for the action log service."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(mongo_uri)
        self._db = self._client[db_name]
        self._configs = self._db["action_log_config"]

    async def ensure_indexes(self) -> None:
        """Create indexes on startup. Safe to call multiple times."""
        await self._configs.create_index([("guild_id", ASCENDING)], unique=True)
        logger.info("MongoActionLogRepository: indexes ensured")

    async def get_config(self, guild_id: int) -> ActionLogConfig | None:
        """Return the action log config for the guild, or None if not configured."""
        try:
            doc = await self._configs.find_one({"guild_id": guild_id}, {"_id": 0})
            return ActionLogConfig.model_validate(doc) if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to fetch action log config for guild {guild_id}: {e}")
            return None

    async def save_config(self, config: ActionLogConfig) -> None:
        """Upsert the action log config for the guild."""
        try:
            doc = config.model_dump(mode="json")
            await self._configs.replace_one(
                {"guild_id": config.guild_id}, doc, upsert=True
            )
        except PyMongoError as e:
            logger.error(
                f"Failed to save action log config for guild {config.guild_id}: {e}"
            )

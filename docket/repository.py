from __future__ import annotations

from loguru import logger
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from docket.models import DocketConfig, DocketPanelRecord, PanelType


class MongoDocketRepository:
    """MongoDB-backed repository for docket config and panel records."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(mongo_uri)
        self._config_col = self._client[db_name]["docket_config"]
        self._panels_col = self._client[db_name]["docket_panels"]

    async def ensure_indexes(self) -> None:
        """Create required unique indexes."""
        await self._config_col.create_index("guild_id", unique=True)
        await self._panels_col.create_index(
            [("guild_id", ASCENDING), ("panel_type", ASCENDING)], unique=True
        )

    async def get_config(self, guild_id: int) -> DocketConfig | None:
        """Retrieve the docket config for a guild."""
        try:
            doc = await self._config_col.find_one({"guild_id": guild_id}, {"_id": 0})
            if doc is None:
                return None
            return DocketConfig.model_validate(doc)
        except PyMongoError:
            logger.exception("DocketRepository: failed to get config")
            return None

    async def save_config(self, config: DocketConfig) -> None:
        """Upsert the docket config for a guild."""
        try:
            doc = config.model_dump(mode="json")
            await self._config_col.replace_one(
                {"guild_id": config.guild_id}, doc, upsert=True
            )
        except PyMongoError:
            logger.exception("DocketRepository: failed to save config")

    async def get_panel_record(
        self, guild_id: int, panel_type: PanelType
    ) -> DocketPanelRecord | None:
        """Retrieve a panel record by guild and type."""
        try:
            doc = await self._panels_col.find_one(
                {"guild_id": guild_id, "panel_type": panel_type.value},
                {"_id": 0},
            )
            if doc is None:
                return None
            return DocketPanelRecord.model_validate(doc)
        except PyMongoError:
            logger.exception("DocketRepository: failed to get panel record")
            return None

    async def get_all_panel_records(self, guild_id: int) -> list[DocketPanelRecord]:
        """Retrieve all panel records for a guild."""
        records: list[DocketPanelRecord] = []
        try:
            async for doc in self._panels_col.find({"guild_id": guild_id}, {"_id": 0}):
                records.append(DocketPanelRecord.model_validate(doc))
        except PyMongoError:
            logger.exception("DocketRepository: failed to get all panel records")
        return records

    async def save_panel_record(self, record: DocketPanelRecord) -> None:
        """Upsert a panel record."""
        try:
            doc = record.model_dump(mode="json")
            await self._panels_col.replace_one(
                {
                    "guild_id": record.guild_id,
                    "panel_type": record.panel_type.value,
                },
                doc,
                upsert=True,
            )
        except PyMongoError:
            logger.exception("DocketRepository: failed to save panel record")

    async def delete_panel_record(self, guild_id: int, panel_type: PanelType) -> None:
        """Delete a panel record."""
        try:
            await self._panels_col.delete_one(
                {"guild_id": guild_id, "panel_type": panel_type.value}
            )
        except PyMongoError:
            logger.exception("DocketRepository: failed to delete panel record")

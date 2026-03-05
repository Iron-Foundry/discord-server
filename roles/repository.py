from __future__ import annotations

from pymongo import ASCENDING, AsyncMongoClient

from roles.models import RolePanel


class MongoRolePanelRepository:
    """MongoDB-backed repository for role panels."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(mongo_uri)
        self._col = self._client[db_name]["role_panels"]

    async def ensure_indexes(self) -> None:
        """Create required indexes."""
        await self._col.create_index("panel_id", unique=True)
        await self._col.create_index(
            [("guild_id", ASCENDING), ("message_id", ASCENDING)]
        )

    async def save_panel(self, panel: RolePanel) -> None:
        """Upsert a panel document."""
        doc = panel.model_dump(mode="json")
        await self._col.replace_one({"panel_id": panel.panel_id}, doc, upsert=True)

    async def delete_panel(self, panel_id: str) -> None:
        """Delete a panel by its ID."""
        await self._col.delete_one({"panel_id": panel_id})

    async def get_panel(self, panel_id: str) -> RolePanel | None:
        """Retrieve a single panel by ID."""
        doc = await self._col.find_one({"panel_id": panel_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return RolePanel.model_validate(doc)

    async def get_all_panels(self, guild_id: int) -> list[RolePanel]:
        """Retrieve all panels for a guild."""
        panels: list[RolePanel] = []
        async for doc in self._col.find({"guild_id": guild_id}):
            doc.pop("_id", None)
            panels.append(RolePanel.model_validate(doc))
        return panels

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import RolePanel as OrmRolePanel
from features.member.roles.models import RolePanel


class PgRolePanelRepository:
    """PostgreSQL-backed repository for role panels."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def ensure_indexes(self) -> None:
        """No-op — indexes are managed by Alembic migrations."""
        logger.info("PgRolePanelRepository: ready")

    async def save_panel(self, panel: RolePanel) -> None:
        """Upsert a panel."""
        now = datetime.now(UTC)
        roles = [r.model_dump(mode="json") for r in panel.roles]
        stmt = (
            pg_insert(OrmRolePanel)
            .values(
                panel_id=panel.panel_id,
                guild_id=panel.guild_id,
                channel_id=panel.channel_id,
                message_id=panel.message_id,
                title=panel.title,
                description=panel.description,
                max_selectable=panel.max_selectable,
                roles=roles,
                created_at=panel.created_at,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["panel_id"],
                set_={
                    "channel_id": panel.channel_id,
                    "message_id": panel.message_id,
                    "title": panel.title,
                    "description": panel.description,
                    "max_selectable": panel.max_selectable,
                    "roles": roles,
                    "updated_at": now,
                },
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def delete_panel(self, panel_id: str) -> None:
        """Delete a panel by its ID."""
        async with self._factory() as session:
            await session.execute(
                delete(OrmRolePanel).where(OrmRolePanel.panel_id == panel_id)
            )
            await session.commit()

    async def get_panel(self, panel_id: str) -> RolePanel | None:
        """Retrieve a single panel by ID."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmRolePanel).where(OrmRolePanel.panel_id == panel_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _orm_to_domain(row)

    async def get_all_panels(self, guild_id: int) -> list[RolePanel]:
        """Retrieve all panels for a guild."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmRolePanel).where(OrmRolePanel.guild_id == guild_id)
            )
            rows = result.scalars().all()
            return [_orm_to_domain(row) for row in rows]


def _orm_to_domain(row: OrmRolePanel) -> RolePanel:
    """Convert ORM row to domain RolePanel."""
    return RolePanel.model_validate(
        {
            "panel_id": row.panel_id,
            "guild_id": row.guild_id,
            "channel_id": row.channel_id,
            "message_id": row.message_id,
            "title": row.title,
            "description": row.description,
            "max_selectable": row.max_selectable,
            "roles": row.roles or [],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )

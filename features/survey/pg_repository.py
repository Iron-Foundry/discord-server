from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.models import SurveyActive
from core.db.models import SurveyResponse as OrmSurveyResponse
from core.db.models import SurveyTemplate as OrmSurveyTemplate
from features.survey.models import ActiveSurvey, SurveyResponse, SurveyTemplate

_ACTIVE_ID = 1


class PgSurveyRepository:
    """PostgreSQL-backed repository for survey templates, state, and responses."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def ensure_indexes(self) -> None:
        """No-op — indexes are managed by Alembic migrations."""
        logger.info("PgSurveyRepository: ready")

    # -------------------------------------------------------------------------
    # Templates
    # -------------------------------------------------------------------------

    async def save_template(self, template: SurveyTemplate) -> None:
        """Upsert a survey template.

        Extra domain fields (guild_id, description, created_by_id) are stored
        inside the ``questions`` JSONB alongside the ``fields`` list.
        """
        questions = {
            "fields": [f.model_dump(mode="json") for f in template.fields],
            "guild_id": template.guild_id,
            "description": template.description,
            "created_by_id": template.created_by_id,
        }
        stmt = (
            pg_insert(OrmSurveyTemplate)
            .values(
                template_id=template.template_id,
                title=template.title,
                questions=questions,
                created_at=template.created_at,
            )
            .on_conflict_do_update(
                index_elements=["template_id"],
                set_={
                    "title": template.title,
                    "questions": questions,
                },
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def get_template(
        self, guild_id: int, template_id: str
    ) -> SurveyTemplate | None:
        """Return a template by ID (guild_id used only for compatibility)."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmSurveyTemplate).where(
                    OrmSurveyTemplate.template_id == template_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _orm_to_template(row)

    async def list_templates(self, guild_id: int) -> list[SurveyTemplate]:
        """Return all templates (guild_id filter omitted — single-guild schema)."""
        async with self._factory() as session:
            result = await session.execute(select(OrmSurveyTemplate))
            rows = result.scalars().all()
            return [_orm_to_template(row) for row in rows]

    async def delete_template(self, guild_id: int, template_id: str) -> None:
        """Delete a template by ID."""
        async with self._factory() as session:
            await session.execute(
                delete(OrmSurveyTemplate).where(
                    OrmSurveyTemplate.template_id == template_id
                )
            )
            await session.commit()

    # -------------------------------------------------------------------------
    # Active survey
    # -------------------------------------------------------------------------

    async def set_active(self, active: ActiveSurvey) -> None:
        """Mark a survey as active (singleton row, id=1)."""
        stmt = (
            pg_insert(SurveyActive)
            .values(
                id=_ACTIVE_ID,
                template_id=active.template_id,
                ticket_id=None,
                started_at=active.activated_at,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "template_id": active.template_id,
                    "started_at": active.activated_at,
                },
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def get_active(self, guild_id: int) -> ActiveSurvey | None:
        """Return the currently active survey, or None."""
        async with self._factory() as session:
            result = await session.execute(
                select(SurveyActive).where(SurveyActive.id == _ACTIVE_ID)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            from datetime import UTC, datetime

            return ActiveSurvey(
                guild_id=guild_id,
                template_id=row.template_id,
                activated_by_id=0,
                activated_at=row.started_at or datetime.now(UTC),
            )

    async def clear_active(self, guild_id: int) -> None:
        """Remove the active survey record."""
        async with self._factory() as session:
            await session.execute(
                delete(SurveyActive).where(SurveyActive.id == _ACTIVE_ID)
            )
            await session.commit()

    # -------------------------------------------------------------------------
    # Responses
    # -------------------------------------------------------------------------

    async def save_response(self, response: SurveyResponse) -> None:
        """Upsert a survey response (full model stored in responses JSONB)."""
        data = response.model_dump(mode="json")
        stmt = (
            pg_insert(OrmSurveyResponse)
            .values(
                ticket_id=response.ticket_id,
                template_id=response.template_id,
                responses=data,
                submitted_at=response.completed_at,
            )
            .on_conflict_do_update(
                index_elements=["ticket_id"],
                set_={
                    "template_id": response.template_id,
                    "responses": data,
                    "submitted_at": response.completed_at,
                },
            )
        )
        async with self._factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def update_response(self, ticket_id: int, **fields: Any) -> None:
        """Partially update a response by merging fields into the responses JSONB."""
        async with self._factory() as session:
            await session.execute(
                text(
                    "UPDATE survey_responses"
                    " SET responses = responses || :data::jsonb"
                    " WHERE ticket_id = :tid"
                ),
                {"data": json.dumps(fields), "tid": ticket_id},
            )
            await session.commit()

    async def get_response(self, ticket_id: int) -> SurveyResponse | None:
        """Return a survey response, or None."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmSurveyResponse).where(
                    OrmSurveyResponse.ticket_id == ticket_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            try:
                return SurveyResponse.model_validate(row.responses)
            except Exception as exc:
                logger.error(
                    "PgSurveyRepository: failed to parse response for ticket {}: {}",
                    ticket_id,
                    exc,
                )
                return None

    async def get_responses_for_template(
        self, guild_id: int, template_id: str
    ) -> list[SurveyResponse]:
        """Return all responses for a template."""
        async with self._factory() as session:
            result = await session.execute(
                select(OrmSurveyResponse).where(
                    OrmSurveyResponse.template_id == template_id
                )
            )
            rows = result.scalars().all()
            responses: list[SurveyResponse] = []
            for row in rows:
                try:
                    responses.append(SurveyResponse.model_validate(row.responses))
                except Exception as exc:
                    logger.warning(
                        "PgSurveyRepository: skipping malformed response for ticket {}: {}",
                        row.ticket_id,
                        exc,
                    )
            return responses

    async def delete_response(self, ticket_id: int) -> None:
        """Delete a response by ticket ID."""
        async with self._factory() as session:
            await session.execute(
                delete(OrmSurveyResponse).where(
                    OrmSurveyResponse.ticket_id == ticket_id
                )
            )
            await session.commit()

    async def delete_responses_for_template(
        self, guild_id: int, template_id: str
    ) -> int:
        """Delete all responses for a template. Returns deleted count."""
        async with self._factory() as session:
            result = await session.execute(
                delete(OrmSurveyResponse).where(
                    OrmSurveyResponse.template_id == template_id
                )
            )
            await session.commit()
            return result.rowcount


def _orm_to_template(row: OrmSurveyTemplate) -> SurveyTemplate:
    """Reconstruct a SurveyTemplate domain model from an ORM row."""
    from datetime import UTC, datetime

    questions: dict = row.questions or {}
    return SurveyTemplate.model_validate(
        {
            "template_id": row.template_id,
            "title": row.title,
            "created_at": row.created_at or datetime.now(UTC),
            "fields": questions.get("fields", []),
            "guild_id": questions.get("guild_id", 0),
            "description": questions.get("description"),
            "created_by_id": questions.get("created_by_id", 0),
        }
    )

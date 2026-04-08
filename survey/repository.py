from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, AsyncMongoClient

from survey.models import ActiveSurvey, SurveyResponse, SurveyTemplate


class MongoSurveyRepository:
    """MongoDB-backed repository for survey templates, state, and responses."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        client = AsyncMongoClient(mongo_uri)
        db = client[db_name]
        self._templates = db["survey_templates"]
        self._active = db["survey_active"]
        self._responses = db["survey_responses"]

    async def ensure_indexes(self) -> None:
        await self._templates.create_index(
            [("guild_id", ASCENDING), ("template_id", ASCENDING)], unique=True
        )
        await self._responses.create_index("ticket_id", unique=True)
        await self._responses.create_index(
            [("guild_id", ASCENDING), ("template_id", ASCENDING)]
        )

    # -------------------------------------------------------------------------
    # Templates
    # -------------------------------------------------------------------------

    async def save_template(self, template: SurveyTemplate) -> None:
        doc = template.model_dump(mode="json")
        await self._templates.replace_one(
            {"guild_id": template.guild_id, "template_id": template.template_id},
            doc,
            upsert=True,
        )

    async def get_template(
        self, guild_id: int, template_id: str
    ) -> SurveyTemplate | None:
        doc = await self._templates.find_one(
            {"guild_id": guild_id, "template_id": template_id}
        )
        if doc is None:
            return None
        doc.pop("_id", None)
        return SurveyTemplate.model_validate(doc)

    async def list_templates(self, guild_id: int) -> list[SurveyTemplate]:
        templates: list[SurveyTemplate] = []
        async for doc in self._templates.find({"guild_id": guild_id}):
            doc.pop("_id", None)
            templates.append(SurveyTemplate.model_validate(doc))
        return templates

    async def delete_template(self, guild_id: int, template_id: str) -> None:
        await self._templates.delete_one(
            {"guild_id": guild_id, "template_id": template_id}
        )

    # -------------------------------------------------------------------------
    # Active survey
    # -------------------------------------------------------------------------

    async def set_active(self, active: ActiveSurvey) -> None:
        doc = active.model_dump(mode="json")
        await self._active.replace_one({"guild_id": active.guild_id}, doc, upsert=True)

    async def get_active(self, guild_id: int) -> ActiveSurvey | None:
        doc = await self._active.find_one({"guild_id": guild_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return ActiveSurvey.model_validate(doc)

    async def clear_active(self, guild_id: int) -> None:
        await self._active.delete_one({"guild_id": guild_id})

    # -------------------------------------------------------------------------
    # Responses
    # -------------------------------------------------------------------------

    async def save_response(self, response: SurveyResponse) -> None:
        doc = response.model_dump(mode="json")
        await self._responses.replace_one(
            {"ticket_id": response.ticket_id}, doc, upsert=True
        )

    async def update_response(self, ticket_id: int, **fields: Any) -> None:
        await self._responses.update_one({"ticket_id": ticket_id}, {"$set": fields})

    async def get_response(self, ticket_id: int) -> SurveyResponse | None:
        doc = await self._responses.find_one({"ticket_id": ticket_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return SurveyResponse.model_validate(doc)

    async def get_responses_for_template(
        self, guild_id: int, template_id: str
    ) -> list[SurveyResponse]:
        responses: list[SurveyResponse] = []
        async for doc in self._responses.find(
            {"guild_id": guild_id, "template_id": template_id}
        ):
            doc.pop("_id", None)
            responses.append(SurveyResponse.model_validate(doc))
        return responses

    async def delete_response(self, ticket_id: int) -> None:
        await self._responses.delete_one({"ticket_id": ticket_id})

    async def delete_responses_for_template(
        self, guild_id: int, template_id: str
    ) -> int:
        result = await self._responses.delete_many(
            {"guild_id": guild_id, "template_id": template_id}
        )
        return result.deleted_count

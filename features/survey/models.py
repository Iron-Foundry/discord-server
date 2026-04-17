from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class SurveyField(BaseModel):
    id: str
    type: Literal["yes_no", "short_text", "long_text", "select"]
    label: str
    description: str | None = None
    required: bool = True
    options: list[str] = []
    max_choices: int = 1


class SurveyTemplate(BaseModel):
    template_id: str
    guild_id: int
    title: str
    description: str | None = None
    fields: list[SurveyField]
    created_at: datetime
    created_by_id: int
    visibility: str | None = None  # Discord role name; None = staff only
    category: Literal["survey", "application"] = "survey"


class ActiveSurvey(BaseModel):
    guild_id: int
    template_id: str
    activated_by_id: int
    activated_at: datetime


class SurveyResponse(BaseModel):
    ticket_id: int
    template_id: str
    respondent_id: int
    guild_id: int
    channel_id: int | None = None
    answers: dict[str, Any] = {}
    completed: bool = False
    started_at: datetime
    completed_at: datetime | None = None
    current_field_index: int = 0
    summary_message_id: int | None = None
    question_message_id: int | None = None

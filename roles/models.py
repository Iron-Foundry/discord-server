from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class SelectableRoleConfig(BaseModel):
    """Configuration for a single selectable role within a panel."""

    role_id: int
    label: str
    description: str = ""
    emoji: str | None = None


class RolePanel(BaseModel):
    """Persistent role panel stored in MongoDB."""

    panel_id: str  # UUID4
    guild_id: int
    channel_id: int
    message_id: int
    title: str
    description: str = ""
    max_selectable: int | None = None  # None = all; 1 = exclusive
    roles: list[SelectableRoleConfig] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

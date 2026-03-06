from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class PanelType(StrEnum):
    """Identifies the type of a docket panel."""

    EVENTS = "events"
    TOC = "toc"
    ACHIEVEMENTS = "achievements"
    DONATIONS = "donations"


class EventEntry(BaseModel):
    """A single scheduled or ongoing event entry."""

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str = ""
    host: str = ""
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    image_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TOCEntry(BaseModel):
    """A single table-of-contents entry linking a channel with a description."""

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    channel_id: int
    description: str
    position: int  # display order, 0-indexed ascending


class DonationEntry(BaseModel):
    """A single donation record."""

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    donor_name: str
    amount: str  # free-text: "50M GP", "Bond", "£10"
    note: str = ""
    donated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocketPanelRecord(BaseModel):
    """Persistent state for a single docket panel, stored in MongoDB."""

    guild_id: int
    panel_type: PanelType
    message_id: int = 0  # 0 = not yet sent
    current_page: int = 0  # pagination state for AchievementsPanel
    event_entries: list[EventEntry] = Field(default_factory=list)
    toc_entries: list[TOCEntry] = Field(default_factory=list)
    donation_entries: list[DonationEntry] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DocketConfig(BaseModel):
    """Guild-level configuration for the docket service."""

    guild_id: int
    channel_id: int
    panel_order: list[PanelType] = Field(default_factory=list)

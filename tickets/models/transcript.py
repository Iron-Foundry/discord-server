import discord
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Any, Protocol


class AttachmentInfo(BaseModel):
    filename: str
    url: str
    size: int
    content_type: str | None = None


class TranscriptEntry(BaseModel):
    message_id: int
    author_id: int
    author_name: str
    author_display_name: str
    author_avatar_url: str
    author_is_bot: bool
    content: str
    timestamp: datetime
    edited_at: datetime | None = None
    attachments: list[AttachmentInfo] = Field(default_factory=list)
    embeds: list[Any] = Field(default_factory=list)

    @classmethod
    def from_discord_message(cls, message: discord.Message) -> "TranscriptEntry":
        return cls(
            message_id=message.id,
            author_id=message.author.id,
            author_name=message.author.name,
            author_display_name=message.author.display_name,
            author_avatar_url=str(message.author.display_avatar.url),
            author_is_bot=message.author.bot,
            content=message.content or "",
            timestamp=message.created_at,
            edited_at=message.edited_at,
            attachments=[
                AttachmentInfo(
                    filename=att.filename,
                    url=att.url,
                    size=att.size,
                    content_type=att.content_type,
                )
                for att in message.attachments
            ],
            embeds=[embed.to_dict() for embed in message.embeds],
        )


class StaffActionType(str, Enum):
    CLOSED = "closed"
    REOPENED = "reopened"
    ADDED_USER = "added_user"
    REMOVED_USER = "removed_user"
    FROZE = "froze"
    UNFROZE = "unfroze"
    TIMED_OUT = "timed_out"


class StaffAction(BaseModel):
    """Records a staff-initiated event inside a ticket."""

    actor_id: int
    actor_name: str
    action: StaffActionType
    target_id: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    note: str | None = None


class Transcript(BaseModel):
    ticket_id: int
    channel_id: int
    guild_id: int
    creator_id: int
    ticket_type: str
    created_at: datetime
    closed_at: datetime | None = None
    close_reason: str | None = None  # DM'd to the ticket creator
    staff_note: str | None = None  # internal only, never shown to user
    closed_by_id: int | None = None
    entries: list[TranscriptEntry] = Field(default_factory=list)
    staff_actions: list[StaffAction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_entry(self, entry: TranscriptEntry) -> None:
        self.entries.append(entry)

    def add_staff_action(self, action: StaffAction) -> None:
        self.staff_actions.append(action)

    def close(self, closed_by_id: int, reason: str | None, note: str | None) -> None:
        self.closed_at = datetime.now(UTC)
        self.closed_by_id = closed_by_id
        self.close_reason = reason
        self.staff_note = note

    def get_duration(self) -> str:
        end = self.closed_at or datetime.now(UTC)
        duration = end - self.created_at
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m"

    def get_message_count(self) -> int:
        return len(self.entries)

    def get_unique_participants(self) -> set[int]:
        return {entry.author_id for entry in self.entries}

    def get_first_staff_response(self, staff_ids: set[int]) -> datetime | None:
        """Return timestamp of the first staff member message (for SLA tracking)."""
        for entry in self.entries:
            if entry.author_id in staff_ids and not entry.author_is_bot:
                return entry.timestamp
        return None


class TranscriptHandler(Protocol):
    """Protocol for pluggable transcript persistence backends."""

    async def save_transcript(self, transcript: Transcript) -> bool: ...
    async def get_transcript(self, ticket_id: int) -> Transcript | None: ...

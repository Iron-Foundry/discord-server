import discord
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Protocol


class TranscriptEntry(BaseModel):
    """Represents a single discord message in a ticket transcript"""

    author: discord.Member | discord.User
    content: str
    timestamp: datetime
    attachments: list[str] = Field(default_factory=list)
    embeds: list[dict[str, Any]] = Field(default_factory=list)
    message_id: int | None = None

    @classmethod
    def from_discord_message(cls, message: discord.Message) -> TranscriptEntry:
        """Create TranscriptEntry from Discord message"""
        return cls(
            author_id=message.author.id,
            author_name=message.author.name,
            author_profile_picture=message.author.display_avatar.url,
            author_display_name=message.author.display_name,
            content=message.content,
            timestamp=message.created_at,
            attachments=[att.filename for att in message.attachments],
            embeds=[embed.to_dict() for embed in message.embeds],
            message_id=message.id,
        )


class Transcript(BaseModel):
    """Model for ticket transcript data"""

    ticket_id: int
    channel_id: int
    creator_id: int
    ticket_type: str
    reason: str = Field(default_factory=str)
    created_at: datetime = Field(default_factory=datetime.now)
    closed_at: datetime | None = None
    entries: list[TranscriptEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_entry(self, entry: TranscriptEntry) -> None:
        """Add an entry to the transcript"""
        self.entries.append(entry)

    def close(self) -> None:
        """Mark transcript as closed"""
        self.closed_at = datetime.now()

    def get_duration(self) -> str:
        """Get formatted duration of ticket"""
        if not self.closed_at:
            duration = datetime.now() - self.created_at
        else:
            duration = self.closed_at - self.created_at

        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m"

    def get_message_count(self) -> int:
        """Get total message count"""
        return len(self.entries)

    def get_unique_participants(self) -> set[int]:
        """Get set of unique participant IDs"""
        return {entry.author_id for entry in self.entries}


class TranscriptHandler(Protocol):
    """Protocol for transcript logging handlers"""

    async def save_transcript(self, transcript: Transcript) -> bool:
        """Save transcript and return success status"""
        ...

    async def get_transcript(self, ticket_id: int) -> Transcript | None:
        """Retrieve a transcript by ticket ID"""
        ...

import asyncio
from collections.abc import Callable, Coroutine
from enum import Enum
from pydantic import BaseModel, Field
import discord
from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Any
from loguru import logger

from .transcript import Transcript, TranscriptEntry


class TicketStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class TicketTeam(BaseModel):
    name: str
    role_id: int

    def get_role(self, guild: discord.Guild) -> discord.Role | None:
        return discord.utils.get(guild.roles, id=self.role_id)

    def is_member(self, member: discord.Member) -> bool:
        return any(role.id == self.role_id for role in member.roles)

    def get_mention_string(self, guild: discord.Guild) -> str:
        role = self.get_role(guild)
        return role.mention if role else ""


class MemberSnapshot(BaseModel):
    """Point-in-time snapshot of a member captured at ticket creation."""

    id: int
    name: str
    display_name: str
    avatar_url: str
    roles: list[dict[str, Any]] = Field(
        default_factory=list
    )  # [{"id": int, "name": str}]

    @classmethod
    def from_member(cls, member: discord.Member) -> "MemberSnapshot":
        return cls(
            id=member.id,
            name=member.name,
            display_name=member.display_name,
            avatar_url=str(member.display_avatar.url),
            roles=[
                {"id": r.id, "name": r.name}
                for r in member.roles
                if r.name != "@everyone"
            ],
        )


class ReopenEvent(BaseModel):
    reopened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reopened_by_id: int


class TicketRecord(BaseModel):
    """MongoDB-serializable representation of a ticket's state."""

    ticket_id: int
    guild_id: int
    channel_id: int
    panel_message_id: int | None = None
    creator: MemberSnapshot
    ticket_type: str
    status: TicketStatus = TicketStatus.OPEN
    timeout_frozen: bool = False
    last_message_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None
    closed_by_id: int | None = None
    close_reason: str | None = None  # DM'd to ticket creator
    staff_note: str | None = None  # internal, never shown to user
    first_staff_response_at: datetime | None = None
    assigned_staff: list[int] = Field(default_factory=list)
    reopen_history: list[ReopenEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)  # type-specific fields


class TicketTypeConfig(ABC):
    """Abstract base class for all ticket types. Subclass this to add a new type."""

    enabled: bool = True

    # --- Required ---

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Unique snake_case ID, e.g. 'rank_up'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the select menu."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description shown in the select menu."""

    @property
    @abstractmethod
    def emoji(self) -> str:
        """Emoji shown alongside the type name."""

    @property
    @abstractmethod
    def color(self) -> discord.Color:
        """Embed accent color for this ticket type."""

    @property
    @abstractmethod
    def teams(self) -> list[TicketTeam]:
        """Staff teams that handle this ticket type (pinged on creation)."""

    @property
    @abstractmethod
    def channel_prefix(self) -> str:
        """Prefix for ticket channel names, e.g. 'rankup' → 'rankup-0001'."""

    # --- Optional overrides ---

    @property
    def category_name(self) -> str | None:
        """Discord category to create the ticket channel under. None = 'Tickets'."""
        return None

    @property
    def max_open_per_user(self) -> int:
        """Max concurrent open tickets a single user may have of this type."""
        return 1

    @property
    def sensitive(self) -> bool:
        """If True, no transcript is collected or persisted for privacy."""
        return False

    # --- Select menu ---

    def build_select_option(self) -> discord.SelectOption:
        return discord.SelectOption(
            label=self.display_name,
            value=self.identifier,
            description=self.description,
            emoji=self.emoji,
        )

    # --- Embed builders ---

    @abstractmethod
    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        """Embed posted inside the ticket channel on creation."""

    def build_close_embed(
        self, record: TicketRecord, closer: discord.Member
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.emoji} Ticket #{record.ticket_id:04d} Closed",
            description=f"**{self.display_name}** ticket has been closed.",
            color=discord.Color.red(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Closed by", value=closer.mention, inline=True)
        embed.add_field(name="Created by", value=f"<@{record.creator.id}>", inline=True)
        embed.add_field(
            name="Duration", value=self._format_duration(record), inline=True
        )
        if record.close_reason:
            embed.add_field(name="Reason", value=record.close_reason, inline=False)
        return embed

    def build_reopen_embed(
        self, record: TicketRecord, reopener: discord.Member
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.emoji} Ticket #{record.ticket_id:04d} Reopened",
            description=f"**{self.display_name}** ticket has been reopened.",
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Reopened by", value=reopener.mention, inline=True)
        return embed

    # --- Channel permissions ---

    def get_channel_permissions(
        self, guild: discord.Guild, creator: discord.Member
    ) -> dict[
        discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
    ]:
        overwrites: dict[
            discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
        ] = {}
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        overwrites[creator] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        )
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            )
        for team in self.teams:
            role = team.get_role(guild)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True,
                )
        return overwrites

    # --- Lifecycle hooks (default no-op) ---

    async def on_created(
        self, record: TicketRecord, channel: discord.TextChannel
    ) -> None:
        """Called after the ticket channel is created and the opening embed is posted."""
        mentions = [
            team.get_mention_string(channel.guild)
            for team in self.teams
            if team.get_mention_string(channel.guild)
        ]
        if mentions:
            await channel.send(" ".join(mentions))

    async def on_closed(
        self,
        record: TicketRecord,
        closer: discord.Member,
        reason: str | None,
        note: str | None,
    ) -> None:
        """Called after the ticket is closed."""

    async def on_reopened(self, record: TicketRecord, reopener: discord.Member) -> None:
        """Called after the ticket is reopened."""

    # --- Optional: initial modal ---

    def build_creation_modal(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> discord.ui.Modal | None:
        """Return a Modal to collect type-specific data, or None to skip."""
        return None

    # --- Helpers ---

    @staticmethod
    def _format_duration(record: TicketRecord) -> str:
        end = record.closed_at or datetime.now(UTC)
        delta = end - record.created_at
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m"


class TicketTypeRegistry:
    """Holds and manages all registered ticket types."""

    def __init__(self) -> None:
        self._types: dict[str, TicketTypeConfig] = {}

    def register(self, ticket_type: TicketTypeConfig) -> None:
        self._types[ticket_type.identifier] = ticket_type
        logger.info(f"Registered ticket type: {ticket_type.display_name}")

    def get(self, identifier: str) -> TicketTypeConfig | None:
        return self._types.get(identifier)

    def get_all(self) -> list[TicketTypeConfig]:
        return list(self._types.values())

    def get_enabled(self) -> list[TicketTypeConfig]:
        return [t for t in self._types.values() if t.enabled]

    def enable(self, identifier: str) -> None:
        if t := self._types.get(identifier):
            t.enabled = True
            logger.info(f"Enabled ticket type: {t.display_name}")

    def disable(self, identifier: str) -> None:
        if t := self._types.get(identifier):
            t.enabled = False
            logger.info(f"Disabled ticket type: {t.display_name}")

    def unregister(self, identifier: str) -> None:
        if identifier in self._types:
            name = self._types[identifier].display_name
            del self._types[identifier]
            logger.info(f"Unregistered ticket type: {name}")


class Ticket:
    """Live in-memory representation of an open (or recently closed) ticket."""

    def __init__(
        self,
        record: TicketRecord,
        channel: discord.TextChannel,
        creator: discord.Member | None,
        ticket_type: TicketTypeConfig,
    ) -> None:
        self.record = record
        self.channel = channel
        self.creator: discord.Member | None = creator
        self.ticket_type = ticket_type
        self.transcript = Transcript(
            ticket_id=record.ticket_id,
            channel_id=record.channel_id,
            guild_id=record.guild_id,
            creator_id=record.creator.id,
            ticket_type=ticket_type.identifier,
            created_at=record.created_at,
        )
        self._timeout_task: asyncio.Task | None = None

    @classmethod
    def from_record(
        cls,
        record: TicketRecord,
        channel: discord.TextChannel,
        ticket_type: TicketTypeConfig,
        creator: discord.Member | None = None,
    ) -> "Ticket":
        """Reconstruct a Ticket from a persisted record (e.g. on restart or reopen)."""
        return cls(
            record=record, channel=channel, creator=creator, ticket_type=ticket_type
        )

    @property
    def ticket_id(self) -> int:
        return self.record.ticket_id

    @property
    def status(self) -> TicketStatus:
        return self.record.status

    @property
    def is_frozen(self) -> bool:
        return self.record.timeout_frozen

    async def collect_messages(self) -> None:
        try:
            async for message in self.channel.history(limit=None, oldest_first=True):
                entry = TranscriptEntry.from_discord_message(message)
                self.transcript.add_entry(entry)
        except Exception as e:
            logger.error(f"Ticket #{self.ticket_id}: failed to collect messages: {e}")

    async def close(
        self, closer: discord.Member, reason: str | None, note: str | None
    ) -> None:
        self.record.status = TicketStatus.CLOSED
        self.record.closed_at = datetime.now(UTC)
        self.record.closed_by_id = closer.id
        self.record.close_reason = reason
        self.record.staff_note = note
        self.transcript.close(closer.id, reason, note)

    async def reopen(self, reopener: discord.Member) -> None:
        self.record.status = TicketStatus.OPEN
        self.record.closed_at = None
        self.record.closed_by_id = None
        self.record.close_reason = None
        self.record.staff_note = None
        self.record.reopen_history.append(ReopenEvent(reopened_by_id=reopener.id))
        self.record.last_message_at = datetime.now(UTC)

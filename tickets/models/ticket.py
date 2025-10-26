from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
import discord
from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Any
from loguru import logger

from .transcript import Transcript, TranscriptEntry, TranscriptHandler


class TicketStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class TicketTeam(BaseModel):
    name: str
    role_id: int

    def get_role(self, guild: discord.Guild) -> discord.Role:
        """Get discord.Role object from ID"""
        for role in guild.roles:
            if role.id == self.role_id:
                return role
        return

    def is_member(self, member: discord.Member) -> bool:
        """Check if member is part of ticket team"""
        return [role.id in self.role_id for role in member.roles]

    def get_mention_string(self, guild: discord.Guild) -> str:
        role = self.get_role(guild)
        return role.mention if role else ""


class TicketTypeConfig(ABC):
    @property
    @abstractmethod
    def identifier(self) -> str:
        """Unique identifier for ticket type"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Display name for buttons & embeds"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description for ticket type"""
        pass

    @property
    @abstractmethod
    def emoji(self) -> str:
        """Emoji for this ticket type"""
        pass

    @property
    @abstractmethod
    def teams(self) -> list[TicketTeam]:
        """Teams that handle this ticket type"""
        pass

    @property
    @abstractmethod
    def color(self) -> discord.Color:
        """Embed color for this ticket type"""
        pass

    @property
    def channel_prefix(self) -> str:
        """Prefix for ticket channel names"""
        pass

    @property
    def category_name(self) -> str | None:
        """Specific category for this ticket type (None = 'ticket')"""
        pass

    @abstractmethod
    def build_create_embed(
        self, ticket_id: int, creator: discord.Member
    ) -> discord.Embed:
        """Build creation embed for this ticket type"""
        pass

    def build_close_embed(
        self, ticket_id: int, closer: discord.Member
    ) -> discord.Embed:
        """Build closure embed for this ticket type"""
        embed = discord.Embed(
            title=f"{self.emoji} #{ticket_id}",
            description=f"{self.identifier} ticket closed.",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="Closed by", value=closer.mention)
        return embed

    def get_channel_permissions(
        self, guild: discord.Guild, creator: discord.Member
    ) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
        """Generate channel permission overwrites"""
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            creator: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }

        for team in self.teams:
            role = team.get_role(guild)
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
            )

        return overwrites

    async def on_ticket_created(
        self, ticket: Ticket, channel: discord.TextChannel
    ) -> None:
        """Hook called after ticket creation"""
        mentions = []
        for team in self.teams:
            mention = team.get_mention_string(channel.guild)
            if mention:
                mentions.append(mention)

        if mentions:
            await channel.send(" ".join(mentions) + " - New ticket opened!")


class TicketConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticket_id: int
    channel_id: int
    creator_id: int
    ticket_type: str
    status: TicketStatus = TicketStatus.OPEN
    created_at: datetime = Field(default_factory=datetime.now(UTC))
    closed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def close(self) -> None:
        """Close the ticket"""
        self.status = TicketStatus.CLOSED
        self.closed_at = datetime.now(UTC)


class Ticket:
    """Represents an individual ticket"""

    def __init__(
        self,
        config: TicketConfig,
        channel: discord.TextChannel,
        creator: discord.Member,
        ticket_type: TicketTypeConfig,
    ):
        self.config = config
        self.channel = channel
        self.creator = creator
        self.ticket_type = ticket_type
        self.transcript = Transcript(
            ticket_id=config.ticket_id,
            channel_id=config.channel_id,
            creator_id=config.creator_id,
            ticket_type=ticket_type.identifier,
            created_at=config.created_at,
        )

    @property
    def ticket_id(self) -> int:
        return self.config.ticket_id

    @property
    def status(self) -> TicketStatus:
        return self.config.status

    async def collect_messages(self) -> None:
        try:
            async for message in self.channel.history(limit=None, oldest_first=True):
                entry = TranscriptEntry.from_discord_message(message)
                self.transcript.add_entry(entry)
        except Exception as e:
            logger.error(f"Failed to collect messages: {e}")

    async def close(self) -> None:
        self.config.close()
        self.transcript.close()


class TicketTypeRegistry:
    """Registry for managing ticket types"""

    def __init__(self):
        self._types: dict[str, TicketTypeConfig] = {}

    def register(self, ticket_type: TicketTypeConfig) -> None:
        """Register a new ticket type"""
        self._types[ticket_type.type_id] = ticket_type
        logger.info(f"Registered ticket type: {ticket_type.display_name}")

    def get(self, type_id: str) -> TicketTypeConfig | None:
        """Get a ticket type by ID"""
        return self._types.get(type_id)

    def get_all(self) -> list[TicketTypeConfig]:
        """Get all registered ticket types"""
        return list(self._types.values())

    def unregister(self, type_id: str) -> None:
        """Unregister a ticket type"""
        if type_id in self._types:
            del self._types[type_id]
            logger.info(f"Unregistered ticket type: {type_id}")


class TicketSystem:
    """Main ticket system manager"""

    def __init__(
        self,
        guild: discord.Guild,
        default_category: discord.CategoryChannel,
        archive: discord.TextChannel,
    ):
        self.guild = guild
        self.default_category = default_category
        self.archive = archive
        self.tickets: dict[int, Ticket] = {}
        self.transcript_handlers: list[TranscriptHandler] = []
        self.type_registry = TicketTypeRegistry()
        self._next_ticket_id = 1
        self._categories: dict[str, discord.CategoryChannel] = {}

    def register_ticket_type(self, ticket_type: TicketTypeConfig) -> None:
        """Register a new ticket type"""
        self.type_registry.register(ticket_type)

    def add_transcript_handler(self, handler: TranscriptHandler) -> None:
        """Add a transcript handler to the system"""
        self.transcript_handlers.append(handler)
        logger.info(f"Added transcript handler: {type(handler).__name__}")

    async def _get_or_create_category(
        self, category_name: str | None
    ) -> discord.CategoryChannel:
        """Get or create a category for tickets"""
        if not category_name:
            return self.default_category

        if category_name in self._categories:
            return self._categories[category_name]

        category = discord.utils.get(self.guild.categories, name=category_name)
        if not category:
            category = await self.guild.create_category(category_name)
            logger.info(f"Created category: {category_name}")

        self._categories[category_name] = category
        return category

    async def create_ticket(
        self,
        creator: discord.Member,
        ticket_type: str,
    ) -> Ticket | None:
        """Create a new ticket"""
        ticket_type = self.type_registry.get(ticket_type)
        if not ticket_type:
            logger.error(f"Invalid ticket type: {ticket_type}")
            return None

        try:
            ticket_id = self._next_ticket_id
            self._next_ticket_id += 1

            config = TicketConfig(
                ticket_id=ticket_id,
                channel_id=0,
                creator_id=creator.id,
                ticket_type=ticket_type,
            )

            category = await self._get_or_create_category(ticket_type.category_name)

            channel_name = f"{ticket_type.channel_prefix}-{ticket_id:04d}"
            overwrites = ticket_type.get_channel_permissions(self.guild, creator)

            channel = await category.create_text_channel(
                name=channel_name, overwrites=overwrites
            )

            config.channel_id = channel.id

            ticket = Ticket(config, channel, creator, ticket_type)
            self.tickets[ticket_id] = ticket

            embed = ticket_type.build_create_embed(ticket_id, creator)

            await channel.send(embed=embed)

            await ticket_type.on_ticket_created(ticket, channel)

            logger.info(
                f"Ticket #{ticket_id} ({ticket_type.display_name}) created by {creator}"
            )

            return ticket

        except Exception as e:
            logger.error(f"Failed to create ticket: {e}")
            return None

    async def close_ticket(self, ticket_id: int, closer: discord.Member) -> bool:
        """Close a ticket and save transcript"""
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            logger.error(f"Ticket #{ticket_id} not found")
            return False

        try:
            await ticket.collect_messages()

            await ticket.close()

            embed = ticket.ticket_type.build_close_embed(ticket_id, closer)
            await self.archive.send(embed)

            for handler in self.transcript_handlers:
                await handler.save_transcript(ticket.transcript)

            del self.tickets[ticket_id]

            logger.info(
                f"Ticket #{ticket_id} ({ticket.ticket_type.display_name}) closed by {closer}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to close ticket: {e}")
            return False

    async def get_ticket_by_channel(self, channel_id: int) -> Ticket | None:
        """Get ticket by channel ID"""
        for ticket in self.tickets.values():
            if ticket.channel.id == channel_id:
                return ticket
        return None

    def get_tickets_by_type(self, identifier: str) -> list[Ticket]:
        """Get all tickets of a specific type"""
        return [
            ticket
            for ticket in self.tickets.values()
            if ticket.ticket_type.identifier == identifier
        ]

    def get_user_tickets(self, user_id: int) -> list[Ticket]:
        """Get all tickets created by a user"""
        return [
            ticket for ticket in self.tickets.values() if ticket.creator.id == user_id
        ]

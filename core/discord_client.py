import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, override

import discord
from discord import app_commands
from loguru import logger

from commands.help_registry import HelpRegistry
from core.command_handler import CommandHandler
from core.config import ConfigInterface, ConfigVars
from core.service_loader import load_all_services

if TYPE_CHECKING:
    from action_log.service import ActionLogService
    from broadcast.service import BroadcastService
    from roles.service import RoleService
    from tickets.ticket_service import TicketService


class DiscordClient(discord.Client):
    def __init__(self, debug: bool = False) -> None:
        super().__init__(intents=discord.Intents.all())
        self.config: ConfigInterface = ConfigInterface()
        self._guild: discord.Guild | None = None
        self.debug: bool = debug
        self.command_handler: CommandHandler = CommandHandler(client=self)
        self.help_registry: HelpRegistry = HelpRegistry()
        self._services_loaded: bool = False
        self._bg_tasks: set[asyncio.Task[Any]] = set()
        self._extra_listeners: dict[
            str, list[Callable[..., Coroutine[Any, Any, None]]]
        ] = {}
        self.ticket_service: TicketService | None = None
        self.role_service: RoleService | None = None
        self.action_log_service: ActionLogService | None = None
        self.broadcast_service: BroadcastService | None = None

    async def _resolve_guild(self) -> None:
        """Look up the configured guild and bind it to the command handler."""
        guild_id_str: str | None = self.config.get_variable(ConfigVars.GUILD_ID)
        if not guild_id_str:
            return
        try:
            self._guild = await self.fetch_guild(int(guild_id_str))
            self.command_handler.guild = self._guild
            logger.info(f"Guild set to: {self._guild.name}")
        except Exception:
            logger.exception(f"Could not fetch guild with ID {guild_id_str}")

    async def _init_services(self) -> None:
        """Fetch mongo credentials once and load all services in parallel."""
        mongo_uri = self.config.get_variable(ConfigVars.MONGO_URI)
        db_name = self.config.get_variable(ConfigVars.MONGO_DB_NAME) or "foundry"

        if not mongo_uri:
            logger.error("MONGO_URI not set — no services will start")
            return

        assert self._guild is not None
        (
            self.ticket_service,
            self.role_service,
            self.action_log_service,
            self.broadcast_service,
        ) = await load_all_services(
            guild=self._guild,
            tree=self.command_handler.tree,
            registry=self.help_registry,
            client=self,
            mongo_uri=mongo_uri,
            db_name=db_name,
        )
        self._services_loaded = True

    @override
    async def setup_hook(self) -> None:
        logger.info("Setting up client...")
        await self._resolve_guild()

        if not self._guild:
            return

        await self._init_services()

    async def on_ready(self) -> None:
        if not self.user:
            logger.error("Failed to connect.")
            return
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        # fetch_guild() (used in setup_hook) returns a static REST snapshot —
        # it has no cached members and doesn't update from gateway events.
        # Replace it with the live gateway-managed guild now that we're connected.
        if self._guild:
            live = self.get_guild(self._guild.id)
            if live:
                self._guild = live
                self._refresh_service_guilds(live)
                logger.debug(f"Guild reference refreshed to live cache ({live.name})")

        if not self._services_loaded and self._guild:
            await self._init_services()

        logger.info(await self.command_handler.sync())

    def _refresh_service_guilds(self, guild: discord.Guild) -> None:
        """Propagate the live gateway guild to all already-loaded services."""
        if self.ticket_service:
            self.ticket_service.guild = guild
            self.ticket_service.try_register_archive_handler()
        if self.role_service:
            self.role_service._guild = guild
        if self.action_log_service:
            self.action_log_service._guild = guild
        if self.broadcast_service:
            self.broadcast_service._guild = guild

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if self.ticket_service:
            await self.ticket_service.handle_message(message)

    def add_listener(
        self,
        func: Callable[..., Coroutine[Any, Any, None]],
        event_name: str,
    ) -> None:
        """Register a dynamic event handler on this client."""
        self._extra_listeners.setdefault(event_name, []).append(func)

    @override
    def dispatch(self, event: str, /, *args: Any, **kwargs: Any) -> None:
        super().dispatch(event, *args, **kwargs)
        for handler in self._extra_listeners.get(f"on_{event}", []):
            task = asyncio.create_task(handler(*args, **kwargs))
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    @property
    def current_guild(self) -> discord.Guild:
        if not self._guild:
            raise RuntimeError("Guild not set")
        return self._guild

    @property
    def tree(self) -> app_commands.CommandTree:
        return self.command_handler.tree

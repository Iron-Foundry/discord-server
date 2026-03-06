from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, override

import discord
from loguru import logger

from commands.help_registry import HelpRegistry
from core.command_handler import CommandHandler
from core.config import ConfigInterface, ConfigVars
from core.service_handler import ServiceHandler
from core.service_loader import load_all_services

if TYPE_CHECKING:
    from action_log.service import ActionLogService
    from broadcast.service import BroadcastService
    from docket.service import DocketService
    from join_roles.service import JoinRoleService
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
        self.service_handler: ServiceHandler = ServiceHandler()
        self._services_loaded: bool = False
        self._bg_tasks: set[asyncio.Task[Any]] = set()
        self._extra_listeners: dict[
            str, list[Callable[..., Coroutine[Any, Any, None]]]
        ] = {}
        # Named references for services called directly from the client
        self.ticket_service: TicketService | None = None
        self.role_service: RoleService | None = None
        self.action_log_service: ActionLogService | None = None
        self.broadcast_service: BroadcastService | None = None
        self.join_role_service: JoinRoleService | None = None
        self.docket_service: DocketService | None = None

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
        services = await load_all_services(
            guild=self._guild,
            tree=self.command_handler.tree,
            registry=self.help_registry,
            client=self,
            mongo_uri=mongo_uri,
            db_name=db_name,
        )
        (
            self.ticket_service,
            self.role_service,
            self.action_log_service,
            self.broadcast_service,
            self.join_role_service,
            self.docket_service,
        ) = services
        self.service_handler.register(*services)
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
        if self._guild:
            live = self.get_guild(self._guild.id)
            if live:
                self._guild = live
                self.service_handler.refresh_guilds(live)
                logger.debug(f"Guild reference refreshed to live cache ({live.name})")

        if not self._services_loaded and self._guild:
            await self._init_services()

        await self.service_handler.run_post_ready()

        logger.info(await self.command_handler.sync())

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
    def tree(self) -> discord.app_commands.CommandTree:
        return self.command_handler.tree

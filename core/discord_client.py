from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, override

import discord
from loguru import logger

from core.command_infra.help_registry import HelpRegistry
from core.command_handler import CommandHandler
from core.config import ConfigInterface, ConfigVars
from core.service_handler import ServiceHandler
from core.service_loader import load_all_services

if TYPE_CHECKING:
    from features.action_log.service import ActionLogService
    from features.broadcast.service import BroadcastService
    from features.tickets.dm_service import DMTicketService
    from features.member.join_roles.service import JoinRoleService
    from features.parties.service import PartyService
    from features.member.roles.service import RoleService
    from features.tickets.ticket_service import TicketService
    from features.user_keys.service import UserKeyService


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
        self.ticket_service: TicketService | None = None
        self.role_service: RoleService | None = None
        self.action_log_service: ActionLogService | None = None
        self.broadcast_service: BroadcastService | None = None
        self.join_role_service: JoinRoleService | None = None
        self.dm_ticket_service: DMTicketService | None = None
        self.user_key_service: UserKeyService | None = None
        self.party_service: PartyService | None = None

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
        """Initialise the PG session factory and load all services in parallel."""
        from core.db import init_db, get_session_factory

        database_url = self.config.get_variable(ConfigVars.DATABASE_URL)
        if not database_url:
            logger.error("DATABASE_URL not set - no services will start")
            return

        await init_db(database_url)

        assert self._guild is not None
        services = await load_all_services(
            guild=self._guild,
            tree=self.command_handler.tree,
            registry=self.help_registry,
            client=self,
            session_factory=get_session_factory(),
        )
        (
            self.ticket_service,
            self.role_service,
            self.action_log_service,
            self.broadcast_service,
            self.join_role_service,
            self.dm_ticket_service,
            self.user_key_service,
            self.party_service,
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

        registered = [
            c.name for c in self.command_handler.tree.get_commands(guild=self._guild)
        ]
        logger.info(f"Commands in tree before sync: {registered}")
        try:
            synced = await self.command_handler.sync()
            logger.info(f"Synced {len(synced)} command(s): {[c.name for c in synced]}")
        except Exception:
            logger.exception("Command sync failed")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild:
            if self.ticket_service:
                await self.ticket_service.handle_message(message)
        else:
            if self.dm_ticket_service:
                await self.dm_ticket_service.handle_dm(message)

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

    @override
    async def close(self) -> None:
        """Shut down the client and release the PG connection pool."""
        from core.db import close_db

        if self.ticket_service and self.ticket_service._http_client:
            await self.ticket_service._http_client.aclose()
        await close_db()
        await super().close()

    @property
    def current_guild(self) -> discord.Guild:
        if not self._guild:
            raise RuntimeError("Guild not set")
        return self._guild

    @property
    def tree(self) -> discord.app_commands.CommandTree:
        return self.command_handler.tree

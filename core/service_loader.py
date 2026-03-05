"""Pure service-loading functions; no access to DiscordClient internals."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from commands.help_registry import HelpRegistry

if TYPE_CHECKING:
    from action_log.service import ActionLogService
    from broadcast.service import BroadcastService
    from core.discord_client import DiscordClient
    from roles.service import RoleService
    from tickets.ticket_service import TicketService


async def load_ticket_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
) -> TicketService:
    """Initialise the ticket service and register its slash commands."""
    from commands.handlers import HandlerGroup
    from commands.handlers import register_help as register_handler_help
    from commands.tickets import TicketGroup, TicketTypeGroup
    from commands.tickets import register_help as register_ticket_help
    from tickets.handlers.database import MongoTicketRepository
    from tickets.ticket_service import TicketService
    from tickets.types import register_all_types

    repo = MongoTicketRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = TicketService(guild=guild, repo=repo)
    register_all_types(service)
    await service.initialize()

    register_ticket_help(registry)
    register_handler_help(registry)
    tree.add_command(TicketGroup(service=service))
    tree.add_command(TicketTypeGroup(service=service))
    tree.add_command(HandlerGroup(service=service))
    logger.info("Ticket service initialised and commands registered")
    return service


async def load_role_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> RoleService:
    """Initialise the role panel service and register its slash commands."""
    from commands.role_panel import RolePanelGroup
    from commands.role_panel import register_help as register_rolepanel_help
    from roles.repository import MongoRolePanelRepository
    from roles.service import RoleService

    repo = MongoRolePanelRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = RoleService(guild=guild, client=client, repo=repo)
    await service.initialize()

    register_rolepanel_help(registry)
    tree.add_command(RolePanelGroup(service=service))
    logger.info("Role panel service initialised and commands registered")
    return service


async def load_action_log_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> ActionLogService:
    """Initialise the action log service and register its slash commands."""
    from action_log.repository import MongoActionLogRepository
    from action_log.service import ActionLogService
    from commands.action_log import ActionLogGroup
    from commands.action_log import register_help as register_actionlog_help

    repo = MongoActionLogRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = ActionLogService(guild=guild, client=client, repo=repo)
    await service.initialize()

    register_actionlog_help(registry)
    tree.add_command(ActionLogGroup(service=service))
    logger.info("Action log service initialised and commands registered")
    return service


async def load_broadcast_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
) -> BroadcastService:
    """Initialise the broadcast service and register its slash commands."""
    from broadcast.repository import MongoBroadcastRepository
    from broadcast.service import BroadcastService
    from commands.broadcast import BroadcastGroup, make_broadcast_context_menu
    from commands.broadcast import register_help as register_broadcast_help

    repo = MongoBroadcastRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = BroadcastService(guild=guild, repo=repo)
    await service.initialize()

    register_broadcast_help(registry)
    tree.add_command(BroadcastGroup(service=service))
    tree.add_command(make_broadcast_context_menu(service=service))
    logger.info("Broadcast service initialised and commands registered")
    return service


def _load_help_command(
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
) -> None:
    from commands.help import make_help_command, register_help

    register_help(registry)
    tree.add_command(make_help_command(registry))
    logger.info("Help command registered")


async def load_all_services(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    client: DiscordClient,
    mongo_uri: str,
    db_name: str,
) -> tuple[TicketService, RoleService, ActionLogService, BroadcastService]:
    """Load all four services in parallel, then register the help command."""
    ticket, role, action_log, broadcast = await asyncio.gather(
        load_ticket_service(guild, tree, registry, mongo_uri, db_name),
        load_role_service(guild, tree, registry, mongo_uri, db_name, client),
        load_action_log_service(guild, tree, registry, mongo_uri, db_name, client),
        load_broadcast_service(guild, tree, registry, mongo_uri, db_name),
    )
    _load_help_command(tree, registry)
    return ticket, role, action_log, broadcast

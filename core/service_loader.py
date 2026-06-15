"""Service loading functions for the Foundry Discord bot.

Loading order:
  1. TicketService           - must load first (other services wire to it)
  2. All independent services - loaded in parallel via asyncio.gather()
  3. DMTicketService          - depends on TicketService, loaded after
  4. Help command             - registered last so all services have added their entries
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.command_infra.help_registry import HelpRegistry

if TYPE_CHECKING:
    from features.action_log.service import ActionLogService
    from features.broadcast.service import BroadcastService
    from features.competition_schedule.service import CompScheduleService
    from core.discord_client import DiscordClient
    from features.tickets.dm_service import DMTicketService
    from features.info_panel.service import InfoPanelService
    from features.member.join_roles.service import JoinRoleService
    from features.parties.service import PartyService
    from features.member.roles.service import RoleService
    from features.tickets.ticket_service import TicketService
    from features.user_keys.service import UserKeyService


async def load_ticket_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    session_factory: async_sessionmaker[AsyncSession],
    client: DiscordClient,
) -> TicketService:
    """Initialise the ticket service and register its slash commands."""
    from core.command_infra.handlers import HandlerGroup
    from core.command_infra.handlers import register_help as register_handler_help
    from features.tickets.commands import TicketGroup, TicketTypeGroup
    from features.tickets.commands import register_help as register_ticket_help
    from features.tickets.events import register as register_ticket_events
    from features.tickets.handlers.pg_repository import PgTicketRepository
    from features.tickets.ticket_service import TicketService
    from features.tickets.types import register_all_types

    repo = PgTicketRepository(session_factory=session_factory)
    service = TicketService(guild=guild, repo=repo, client=client)
    register_all_types(service)
    await service.initialize()

    register_ticket_events(service, client)
    register_ticket_help(registry)
    register_handler_help(registry)
    tree.add_command(TicketGroup(service=service), guild=guild)
    tree.add_command(TicketTypeGroup(service=service), guild=guild)
    tree.add_command(HandlerGroup(service=service), guild=guild)
    logger.info("Ticket service initialised and commands registered")
    return service


async def load_role_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    session_factory: async_sessionmaker[AsyncSession],
    client: DiscordClient,
) -> RoleService:
    """Initialise the role panel service and register its slash commands."""
    from features.member.roles.commands import RolePanelGroup
    from features.member.roles.commands import register_help as register_rolepanel_help
    from features.member.roles.pg_repository import PgRolePanelRepository
    from features.member.roles.service import RoleService

    repo = PgRolePanelRepository(session_factory=session_factory)
    service = RoleService(guild=guild, client=client, repo=repo)
    await service.initialize()

    register_rolepanel_help(registry)
    tree.add_command(RolePanelGroup(service=service), guild=guild)
    logger.info("Role panel service initialised and commands registered")
    return service


async def load_action_log_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    session_factory: async_sessionmaker[AsyncSession],
    client: DiscordClient,
) -> ActionLogService:
    """Initialise the action log service and register its slash commands."""
    from features.action_log.pg_repository import PgActionLogRepository
    from features.action_log.service import ActionLogService
    from features.action_log.commands import ActionLogGroup
    from features.action_log.commands import register_help as register_actionlog_help

    repo = PgActionLogRepository(session_factory=session_factory)
    service = ActionLogService(guild=guild, client=client, repo=repo)
    await service.initialize()

    register_actionlog_help(registry)
    tree.add_command(ActionLogGroup(service=service), guild=guild)
    logger.info("Action log service initialised and commands registered")
    return service


async def load_join_role_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    session_factory: async_sessionmaker[AsyncSession],
    client: DiscordClient,
) -> JoinRoleService:
    """Initialise the join role service and register its slash commands."""
    from features.member.join_roles.commands import JoinRoleGroup
    from features.member.join_roles.commands import (
        register_help as register_joinrole_help,
    )
    from features.member.join_roles.events import register as register_join_role_events
    from features.member.join_roles.pg_repository import PgJoinRoleRepository
    from features.member.join_roles.service import JoinRoleService

    repo = PgJoinRoleRepository(session_factory=session_factory)
    service = JoinRoleService(guild=guild, repo=repo)
    await service.initialize()

    register_join_role_events(service, client)
    register_joinrole_help(registry)
    tree.add_command(JoinRoleGroup(service=service), guild=guild)
    logger.info("Join role service initialised and commands registered")
    return service


async def load_broadcast_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    session_factory: async_sessionmaker[AsyncSession],
) -> BroadcastService:
    """Initialise the broadcast service and register its slash commands."""
    from features.broadcast.pg_repository import PgBroadcastRepository
    from features.broadcast.service import BroadcastService
    from features.broadcast.commands import BroadcastGroup, make_broadcast_context_menu
    from features.broadcast.commands import register_help as register_broadcast_help

    repo = PgBroadcastRepository(session_factory=session_factory)
    service = BroadcastService(guild=guild, repo=repo)
    await service.initialize()

    register_broadcast_help(registry)
    tree.add_command(BroadcastGroup(service=service), guild=guild)
    tree.add_command(make_broadcast_context_menu(service=service), guild=guild)
    logger.info("Broadcast service initialised and commands registered")
    return service


async def load_user_key_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    session_factory: async_sessionmaker[AsyncSession],
    client: DiscordClient,
) -> "UserKeyService":
    """Initialise the user key service and register the /userkey command."""
    from features.account.commands import AccountGroup
    from features.user_keys.commands import make_privacy_command, make_userkey_command
    from features.user_keys.pg_repository import PgUserKeyRepository
    from features.user_keys.service import UserKeyService

    repo = PgUserKeyRepository(session_factory=session_factory)
    service = UserKeyService(guild=guild, repo=repo)
    await service.initialize()
    service.register_events(client)

    tree.add_command(make_userkey_command(service), guild=guild)
    tree.add_command(make_privacy_command(service), guild=guild)
    tree.add_command(AccountGroup(service=service), guild=guild)
    logger.info(
        "User key service initialised and /userkey, /privacy, /account commands registered"
    )
    return service


async def load_info_panel_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    session_factory: async_sessionmaker[AsyncSession],
    client: DiscordClient,
) -> "InfoPanelService":
    """Initialise the info panel service and register /infopanel commands."""
    from features.info_panel.commands import InfoPanelGroup
    from features.info_panel.pg_repository import PgInfoPanelRepository
    from features.info_panel.service import InfoPanelService

    repo = PgInfoPanelRepository(session_factory=session_factory)
    service = InfoPanelService(guild=guild, repo=repo, client=client)
    await service.initialize()

    tree.add_command(InfoPanelGroup(service=service), guild=guild)
    logger.info("Info panel service initialised and /infopanel commands registered")
    return service


async def load_party_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    session_factory: async_sessionmaker[AsyncSession],
    client: DiscordClient,
) -> "PartyService":
    """Initialise the party panel service and register /party commands."""
    from features.parties.commands import PartyGroup
    from features.parties.pg_repository import PgPartyRepository
    from features.parties.service import PartyService

    repo = PgPartyRepository(session_factory=session_factory)
    service = PartyService(guild=guild, repo=repo, client=client)
    await service.initialize()

    tree.add_command(PartyGroup(service=service), guild=guild)
    logger.info("Party service initialised and /party commands registered")
    return service


async def load_competition_schedule_service(
    guild: discord.Guild,
    client: "DiscordClient",
) -> "CompScheduleService":
    """Initialise the competition schedule service."""
    from features.competition_schedule.service import CompScheduleService

    service = CompScheduleService(guild=guild, client=client)
    await service.initialize()
    logger.info("Competition schedule service initialised")
    return service


async def load_dm_ticket_service(
    guild: discord.Guild,
    ticket_service: TicketService,
) -> DMTicketService:
    """Initialise the DM ticket service (depends on TicketService)."""
    from features.tickets.dm_service import DMTicketService

    service = DMTicketService(guild=guild, ticket_service=ticket_service)
    await service.initialize()
    logger.info("DM ticket service initialised")
    return service


def _load_help_command(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
) -> None:
    from core.command_infra.help import make_help_command, register_help

    register_help(registry)
    tree.add_command(make_help_command(registry), guild=guild)
    logger.info("Help command registered")


async def load_all_services(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    client: DiscordClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[
    TicketService,
    RoleService,
    ActionLogService,
    BroadcastService,
    JoinRoleService,
    DMTicketService,
    "UserKeyService",
    "PartyService",
    "InfoPanelService",
    "CompScheduleService",
]:
    """Load all services, then register the help command.

    Independent services are loaded in parallel.  :class:`DMTicketService`
    is loaded after :class:`TicketService` because it depends on it.
    """
    # ── 1 & 2. Ticket infrastructure + independent feature services (parallel) ─
    _results = await asyncio.gather(
        load_ticket_service(guild, tree, registry, session_factory, client),
        load_role_service(guild, tree, registry, session_factory, client),
        load_action_log_service(guild, tree, registry, session_factory, client),
        load_broadcast_service(guild, tree, registry, session_factory),
        load_join_role_service(guild, tree, registry, session_factory, client),
        load_user_key_service(guild, tree, session_factory, client),
        load_party_service(guild, tree, session_factory, client),
        load_info_panel_service(guild, tree, session_factory, client),
        load_competition_schedule_service(guild, client),
    )
    ticket = cast("TicketService", _results[0])
    role = cast("RoleService", _results[1])
    action_log = cast("ActionLogService", _results[2])
    broadcast = cast("BroadcastService", _results[3])
    join_role = cast("JoinRoleService", _results[4])
    user_keys = cast("UserKeyService", _results[5])
    parties = cast("PartyService", _results[6])
    info_panel = cast("InfoPanelService", _results[7])
    comp_schedule = cast("CompScheduleService", _results[8])

    dm_ticket = await load_dm_ticket_service(guild, ticket)

    _load_help_command(guild, tree, registry)
    return (
        ticket,
        role,
        action_log,
        broadcast,
        join_role,
        dm_ticket,
        user_keys,
        parties,
        info_panel,
        comp_schedule,
    )

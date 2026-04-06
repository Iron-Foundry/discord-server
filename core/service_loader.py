"""Pure service-loading functions; no access to DiscordClient internals."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from command_infra.help_registry import HelpRegistry

if TYPE_CHECKING:
    from action_log.service import ActionLogService
    from broadcast.service import BroadcastService
    from core.discord_client import DiscordClient
    from dm_tickets.service import DMTicketService
    from join_roles.service import JoinRoleService
    from roles.service import RoleService
    from survey.service import SurveyService
    from tickets.ticket_service import TicketService


async def load_ticket_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> TicketService:
    """Initialise the ticket service and register its slash commands."""
    from command_infra.handlers import HandlerGroup
    from command_infra.handlers import register_help as register_handler_help
    from tickets.commands import TicketGroup, TicketTypeGroup
    from tickets.commands import register_help as register_ticket_help
    from tickets.handlers.database import MongoTicketRepository
    from tickets.ticket_service import TicketService
    from tickets.types import register_all_types

    repo = MongoTicketRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = TicketService(guild=guild, repo=repo, client=client)
    register_all_types(service)
    await service.initialize()

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
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> RoleService:
    """Initialise the role panel service and register its slash commands."""
    from roles.commands import RolePanelGroup
    from roles.commands import register_help as register_rolepanel_help
    from roles.repository import MongoRolePanelRepository
    from roles.service import RoleService

    repo = MongoRolePanelRepository(mongo_uri=mongo_uri, db_name=db_name)
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
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> ActionLogService:
    """Initialise the action log service and register its slash commands."""
    from action_log.repository import MongoActionLogRepository
    from action_log.service import ActionLogService
    from action_log.commands import ActionLogGroup
    from action_log.commands import register_help as register_actionlog_help

    repo = MongoActionLogRepository(mongo_uri=mongo_uri, db_name=db_name)
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
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> JoinRoleService:
    """Initialise the join role service and register its slash commands."""
    from join_roles.commands import JoinRoleGroup
    from join_roles.commands import register_help as register_joinrole_help
    from join_roles.events import register as register_join_role_events
    from join_roles.repository import MongoJoinRoleRepository
    from join_roles.service import JoinRoleService

    repo = MongoJoinRoleRepository(mongo_uri=mongo_uri, db_name=db_name)
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
    mongo_uri: str,
    db_name: str,
) -> BroadcastService:
    """Initialise the broadcast service and register its slash commands."""
    from broadcast.repository import MongoBroadcastRepository
    from broadcast.service import BroadcastService
    from broadcast.commands import BroadcastGroup, make_broadcast_context_menu
    from broadcast.commands import register_help as register_broadcast_help

    repo = MongoBroadcastRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = BroadcastService(guild=guild, repo=repo)
    await service.initialize()

    register_broadcast_help(registry)
    tree.add_command(BroadcastGroup(service=service), guild=guild)
    tree.add_command(make_broadcast_context_menu(service=service), guild=guild)
    logger.info("Broadcast service initialised and commands registered")
    return service


async def load_survey_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> SurveyService:
    """Initialise the survey service and register its slash commands."""
    from survey.commands import SurveyGroup
    from survey.commands import register_help as register_survey_help
    from survey.repository import MongoSurveyRepository
    from survey.service import SurveyService

    repo = MongoSurveyRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = SurveyService(guild=guild, client=client, repo=repo)
    await service.initialize()

    register_survey_help(registry)
    tree.add_command(SurveyGroup(service=service), guild=guild)
    logger.info("Survey service initialised and commands registered")
    return service


async def load_dm_ticket_service(
    guild: discord.Guild,
    ticket_service: TicketService,
) -> DMTicketService:
    """Initialise the DM ticket service (depends on TicketService)."""
    from dm_tickets.service import DMTicketService

    service = DMTicketService(guild=guild, ticket_service=ticket_service)
    await service.initialize()
    logger.info("DM ticket service initialised")
    return service


def _load_help_command(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
) -> None:
    from command_infra.help import make_help_command, register_help

    register_help(registry)
    tree.add_command(make_help_command(registry), guild=guild)
    logger.info("Help command registered")


async def load_all_services(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    client: DiscordClient,
    mongo_uri: str,
    db_name: str,
) -> tuple[
    TicketService,
    RoleService,
    ActionLogService,
    BroadcastService,
    JoinRoleService,
    DMTicketService,
    SurveyService,
]:
    """Load all services, then register the help command.

    Independent services are loaded in parallel.  :class:`DMTicketService`
    is loaded after :class:`TicketService` because it depends on it.
    :class:`SurveyService` is wired to :class:`TicketService` after both
    are loaded so the survey ticket type can be registered.
    """
    from core.config import ConfigInterface, ConfigVars

    ticket, role, action_log, broadcast, join_role, survey = await asyncio.gather(
        load_ticket_service(guild, tree, registry, mongo_uri, db_name, client),
        load_role_service(guild, tree, registry, mongo_uri, db_name, client),
        load_action_log_service(guild, tree, registry, mongo_uri, db_name, client),
        load_broadcast_service(guild, tree, registry, mongo_uri, db_name),
        load_join_role_service(guild, tree, registry, mongo_uri, db_name, client),
        load_survey_service(guild, tree, registry, mongo_uri, db_name, client),
    )

    # Wire survey → ticket after both are ready
    cfg = ConfigInterface()
    staff_id_str = cfg.get_variable(ConfigVars.STAFF_ROLE_ID)
    staff_id = int(staff_id_str) if staff_id_str else 0
    survey.set_ticket_service(ticket, staff_id)

    dm_ticket = await load_dm_ticket_service(guild, ticket)
    _load_help_command(guild, tree, registry)
    return ticket, role, action_log, broadcast, join_role, dm_ticket, survey

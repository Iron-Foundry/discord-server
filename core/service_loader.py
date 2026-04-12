"""Service loading functions for the Foundry Discord bot.

Loading order:
  1. TicketService           — must load first (other services wire to it)
  2. All independent services — loaded in parallel via asyncio.gather()
  3. Ticket type wiring       — survey and application register their ticket types
  4. Session restoration      — re-attach in-progress survey/application flows
  5. DMTicketService          — depends on TicketService, loaded after wiring
  6. Help command             — registered last so all services have added their entries
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from loguru import logger

from core.command_infra.help_registry import HelpRegistry

if TYPE_CHECKING:
    from features.action_log.service import ActionLogService
    from features.broadcast.service import BroadcastService
    from core.discord_client import DiscordClient
    from features.tickets.application_service import ApplicationService
    from features.tickets.dm_service import DMTicketService
    from features.member.join_roles.service import JoinRoleService
    from features.member.roles.service import RoleService
    from features.survey.service import SurveyService
    from features.tickets.ticket_service import TicketService
    from features.user_keys.service import UserKeyService


async def load_ticket_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> TicketService:
    """Initialise the ticket service and register its slash commands."""
    from core.command_infra.handlers import HandlerGroup
    from core.command_infra.handlers import register_help as register_handler_help
    from features.tickets.commands import TicketGroup, TicketTypeGroup
    from features.tickets.commands import register_help as register_ticket_help
    from features.tickets.handlers.database import MongoTicketRepository
    from features.tickets.ticket_service import TicketService
    from features.tickets.types import register_all_types

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
    from features.member.roles.commands import RolePanelGroup
    from features.member.roles.commands import register_help as register_rolepanel_help
    from features.member.roles.repository import MongoRolePanelRepository
    from features.member.roles.service import RoleService

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
    from features.action_log.repository import MongoActionLogRepository
    from features.action_log.service import ActionLogService
    from features.action_log.commands import ActionLogGroup
    from features.action_log.commands import register_help as register_actionlog_help

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
    from features.member.join_roles.commands import JoinRoleGroup
    from features.member.join_roles.commands import (
        register_help as register_joinrole_help,
    )
    from features.member.join_roles.events import register as register_join_role_events
    from features.member.join_roles.repository import MongoJoinRoleRepository
    from features.member.join_roles.service import JoinRoleService

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
    from features.broadcast.repository import MongoBroadcastRepository
    from features.broadcast.service import BroadcastService
    from features.broadcast.commands import BroadcastGroup, make_broadcast_context_menu
    from features.broadcast.commands import register_help as register_broadcast_help

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
    from features.survey.commands import SurveyGroup
    from features.survey.commands import register_help as register_survey_help
    from features.survey.repository import MongoSurveyRepository
    from features.survey.service import SurveyService

    repo = MongoSurveyRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = SurveyService(guild=guild, client=client, repo=repo)
    await service.initialize()

    register_survey_help(registry)
    tree.add_command(SurveyGroup(service=service), guild=guild)
    logger.info("Survey service initialised and commands registered")
    return service


async def load_application_service(
    guild: discord.Guild,
    mongo_uri: str,
    db_name: str,
) -> "ApplicationService":
    """Initialise the application service (staff & mentor step-through flows)."""
    from features.tickets.application_service import ApplicationService
    from features.survey.repository import MongoSurveyRepository

    repo = MongoSurveyRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = ApplicationService(guild=guild, repo=repo)
    await service.initialize()
    return service


async def load_user_key_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    mongo_uri: str,
    db_name: str,
) -> "UserKeyService":
    """Initialise the user key service and register the /userkey command."""
    from features.account.commands import AccountGroup
    from features.user_keys.commands import make_privacy_command, make_userkey_command
    from features.user_keys.repository import MongoUserKeyRepository
    from features.user_keys.service import UserKeyService

    repo = MongoUserKeyRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = UserKeyService(guild=guild, repo=repo)
    await service.initialize()

    tree.add_command(make_userkey_command(service), guild=guild)
    tree.add_command(make_privacy_command(service), guild=guild)
    tree.add_command(AccountGroup(service=service), guild=guild)
    logger.info(
        "User key service initialised and /userkey, /privacy, /account commands registered"
    )
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
    mongo_uri: str,
    db_name: str,
) -> tuple[
    TicketService,
    RoleService,
    ActionLogService,
    BroadcastService,
    JoinRoleService,
    DMTicketService,
    "UserKeyService",
    SurveyService,
    "ApplicationService",
]:
    """Load all services, then register the help command.

    Independent services are loaded in parallel.  :class:`DMTicketService`
    is loaded after :class:`TicketService` because it depends on it.
    :class:`SurveyService` and :class:`ApplicationService` are wired to
    :class:`TicketService` after both are loaded so their ticket types can
    be registered.
    """
    from core.config import ConfigInterface, ConfigVars

    # ── 1 & 2. Ticket infrastructure + independent feature services (parallel) ─
    _results = await asyncio.gather(
        load_ticket_service(guild, tree, registry, mongo_uri, db_name, client),
        load_role_service(guild, tree, registry, mongo_uri, db_name, client),
        load_action_log_service(guild, tree, registry, mongo_uri, db_name, client),
        load_broadcast_service(guild, tree, registry, mongo_uri, db_name),
        load_join_role_service(guild, tree, registry, mongo_uri, db_name, client),
        load_user_key_service(guild, tree, mongo_uri, db_name),
        load_survey_service(guild, tree, registry, mongo_uri, db_name, client),
        load_application_service(guild, mongo_uri, db_name),
    )
    ticket = cast("TicketService", _results[0])
    role = cast("RoleService", _results[1])
    action_log = cast("ActionLogService", _results[2])
    broadcast = cast("BroadcastService", _results[3])
    join_role = cast("JoinRoleService", _results[4])
    user_keys = cast("UserKeyService", _results[5])
    survey = cast("SurveyService", _results[6])
    application = cast("ApplicationService", _results[7])

    cfg = ConfigInterface()

    def _role_id(var: ConfigVars) -> int:
        val = cfg.get_variable(var)
        return int(val) if val else 0

    # ── 3. Ticket type wiring ─────────────────────────────────────────────────
    senior_staff_id = _role_id(ConfigVars.SENIOR_STAFF_ROLE_ID)
    survey.set_ticket_service(ticket, senior_staff_id)
    application.register_ticket_types(
        ticket_service=ticket,
        senior_staff_role_id=senior_staff_id,
        staff_role_id=_role_id(ConfigVars.STAFF_ROLE_ID),
    )

    # ── 4. Session restoration ────────────────────────────────────────────────
    await survey.restore_sessions()
    await application.restore_sessions()

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
        survey,
        application,
    )

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from core.discord_client import DiscordClient
    from join_roles.service import JoinRoleService


def register(service: JoinRoleService, client: DiscordClient) -> None:
    """Register the on_member_join handler to assign configured roles."""

    async def on_member_join(member: discord.Member) -> None:
        logger.debug(f"JoinRole: on_member_join triggered for {member.display_name}")
        await service.assign_roles(member)

    client.add_listener(on_member_join, "on_member_join")

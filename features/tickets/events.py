from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger

from core.common.ticket_types import TicketTypeId

if TYPE_CHECKING:
    from core.discord_client import DiscordClient
    from features.tickets.ticket_service import TicketService


def register(service: TicketService, client: DiscordClient) -> None:
    """Register event listeners for automated ticket triggers."""

    async def on_member_join(member: discord.Member) -> None:
        if member.guild.id != service.guild.id or member.bot:
            return
        logger.debug(f"Tickets[events]: auto-opening join_cc ticket for {member}")
        ticket = await service.create_ticket(
            None,
            TicketTypeId.JOIN_CC.value,
            {"auto_created": True},
            creator_override=member,
        )
        if ticket is None:
            logger.warning(f"Tickets[events]: failed to open join_cc ticket for {member}")

    client.add_listener(on_member_join, "on_member_join")

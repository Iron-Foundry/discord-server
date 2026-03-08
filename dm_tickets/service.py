from __future__ import annotations

import discord
from loguru import logger

from core.service_base import Service

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService


class DMTicketService(Service):
    """Handles ticket creation and reopens initiated from bot DMs.

    Listens for incoming DMs from guild members and responds with an
    interactive menu for opening or reopening tickets.  All ticket
    operations are delegated to :class:`TicketService`.
    """

    def __init__(self, guild: discord.Guild, ticket_service: TicketService) -> None:
        self._guild = guild
        self._ticket_service = ticket_service

    async def initialize(self) -> None:
        """No-op — no async setup required."""
        logger.info("DMTicketService initialised")

    async def handle_dm(self, message: discord.Message) -> None:
        """Process an incoming DM and respond with the ticket menu.

        Silently ignores bots and users who are not members of the guild.
        """
        if message.author.bot:
            return

        member = self._guild.get_member(message.author.id)
        if not member:
            await message.channel.send(
                "You must be a member of the Iron Foundry server"
                " to manage tickets here."
            )
            return

        from dm_tickets.views import DMMenuView, build_dm_menu_embed

        embed = build_dm_menu_embed()
        view = DMMenuView(self._ticket_service, member)
        await message.channel.send(embed=embed, view=view)
        logger.debug(f"DM ticket menu sent to {member} ({member.id})")

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord

from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketRecord, TicketTeam, TicketTypeConfig

if TYPE_CHECKING:
    from applications.service import ApplicationService


class ApplyStaffTicket(TicketTypeConfig):
    """Staff application ticket.

    Uses a step-through question flow instead of an upfront modal.
    The ticket remains open after submission so Senior Staff can review.
    """

    def __init__(
        self, senior_staff_role_id: int, application_service: "ApplicationService"
    ) -> None:
        self._teams = [TicketTeam(name="Senior Staff", role_id=senior_staff_role_id)]
        self._service = application_service

    @property
    def identifier(self) -> str:
        return TicketTypeId.APPLY_STAFF.value

    @property
    def display_name(self) -> str:
        return "Apply to Staff"

    @property
    def description(self) -> str:
        return "Apply to become a staff member."

    @property
    def emoji(self) -> str:
        return "🛡️"

    @property
    def color(self) -> discord.Color:
        return discord.Color.red()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "staff"

    @property
    def category_name(self) -> str:
        return "Staff Applications"

    def build_creation_modal(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> discord.ui.Modal | None:
        return None

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.emoji} Staff Application — #{record.ticket_id:04d}",
            description=(
                "Welcome! Please answer the questions below.\n"
                "Senior Staff will review your responses and get back to you here."
            ),
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Applicant", value=f"<@{record.creator.id}>", inline=True)
        return embed

    async def on_reopened(self, record: TicketRecord, reopener: discord.Member) -> None:
        await self._service.restore_session(record.ticket_id, record.channel_id)

    async def on_created(
        self, record: TicketRecord, channel: discord.TextChannel
    ) -> None:
        mentions = [
            team.get_mention_string(channel.guild)
            for team in self.teams
            if team.get_mention_string(channel.guild)
        ]
        if mentions:
            await channel.send(" ".join(mentions))
        await self._service.start_application(
            type_id=self.identifier,
            channel=channel,
            ticket_id=record.ticket_id,
            applicant_id=record.creator.id,
            guild_id=record.guild_id,
        )

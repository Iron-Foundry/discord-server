from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord

from core.common.ticket_types import TicketTypeId
from features.tickets.models.ticket import TicketRecord, TicketTeam, TicketTypeConfig

if TYPE_CHECKING:
    from features.survey.service import SurveyService


class SurveyTicket(TicketTypeConfig):
    """Survey / feedback ticket type.

    Stepped question flow happens inside the ticket channel; no creation modal.
    The type is disabled by default and enabled only when a survey is activated
    via ``/survey activate``.
    """

    def __init__(
        self, senior_staff_role_id: int, survey_service: "SurveyService"
    ) -> None:
        self._teams = [TicketTeam(name="Senior Staff", role_id=senior_staff_role_id)]
        self._service = survey_service

    @property
    def identifier(self) -> str:
        return TicketTypeId.SURVEY.value

    @property
    def display_name(self) -> str:
        template = self._service.current_template
        return template.title if template else "Survey / Feedback"

    @property
    def description(self) -> str:
        template = self._service.current_template
        if template and template.description:
            return template.description[:100]
        return "Participate in the current community survey."

    @property
    def emoji(self) -> str:
        return "📋"

    @property
    def color(self) -> discord.Color:
        return discord.Color.blurple()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "survey"

    @property
    def max_open_per_user(self) -> int:
        return 1

    def build_creation_modal(
        self,
        callback: Callable[
            [discord.Interaction, dict[str, Any]], Coroutine[Any, Any, Any]
        ],
    ) -> discord.ui.Modal | None:
        return None  # The step-through flow starts inside the ticket channel.

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        template = self._service.current_template
        title = template.title if template else "Survey"
        desc = template.description if template else None

        embed = discord.Embed(
            title=f"📋 {title} — #{record.ticket_id:04d}",
            description=desc,
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Respondent", value=f"<@{record.creator.id}>", inline=True)
        if template:
            total = len(template.fields)
            required = sum(1 for f in template.fields if f.required)
            embed.add_field(
                name="Fields",
                value=f"{total} total, {required} required",
                inline=True,
            )
        embed.set_footer(text="The bot will step you through each question below.")
        return embed

    async def on_reopened(self, record: TicketRecord, reopener: discord.Member) -> None:
        await self._service.restore_session(record.ticket_id, record.channel_id)

    async def on_created(
        self, record: TicketRecord, channel: discord.TextChannel
    ) -> None:
        await self._service.start_survey(
            channel=channel,
            ticket_id=record.ticket_id,
            respondent_id=record.creator.id,
            guild_id=record.guild_id,
        )

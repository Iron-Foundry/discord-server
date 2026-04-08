from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from core.common.ticket_types import TicketTypeId
from core.service_base import Service
from features.survey.models import SurveyResponse, SurveyTemplate
from features.survey.repository import MongoSurveyRepository
from features.survey.views.summary_view import build_summary_embed
from features.tickets.types.event_team_template import build_event_team_template
from features.tickets.types.mentor_template import build_mentor_template
from features.tickets.types.staff_template import build_staff_template

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService


class ApplicationService(Service):
    """Manages step-through question flows for staff and mentor applications.

    Structurally mirrors :class:`survey.service.SurveyService` but uses
    hardcoded templates and does **not** auto-close tickets on submission —
    staff must review and close the ticket themselves.
    """

    def __init__(self, guild: discord.Guild, repo: MongoSurveyRepository) -> None:
        self._guild = guild
        self._repo = repo
        self._ticket_service: TicketService | None = None
        self._templates: dict[str, SurveyTemplate] = {
            TicketTypeId.APPLY_STAFF.value: build_staff_template(guild.id),
            TicketTypeId.APPLY_MENTOR.value: build_mentor_template(guild.id),
            TicketTypeId.APPLY_EVENT_TEAM.value: build_event_team_template(guild.id),
        }

        # Per-ticket in-memory state
        self._sessions: dict[int, SurveyResponse] = {}
        self._channels: dict[int, discord.TextChannel] = {}
        self._summary_messages: dict[int, discord.Message] = {}
        self._question_messages: dict[int, discord.Message] = {}
        self._session_types: dict[int, str] = {}  # ticket_id → type_id

    async def initialize(self) -> None:
        """No-op — no async setup required."""
        logger.info("ApplicationService initialised")

    # -------------------------------------------------------------------------
    # Wiring
    # -------------------------------------------------------------------------

    def register_ticket_types(
        self,
        ticket_service: "TicketService",
        senior_staff_role_id: int,
        staff_role_id: int,
    ) -> None:
        """Register the application ticket types with the ticket registry.

        Called from the service loader after both services are initialised.
        """
        from features.tickets.types.apply_event_team import ApplyEventTeamTicket
        from features.tickets.types.apply_mentor import ApplyMentorTicket
        from features.tickets.types.apply_staff import ApplyStaffTicket

        self._ticket_service = ticket_service
        ticket_service.type_registry.register(
            ApplyStaffTicket(
                senior_staff_role_id=senior_staff_role_id, application_service=self
            )
        )
        ticket_service.type_registry.register(
            ApplyMentorTicket(staff_role_id=staff_role_id, application_service=self)
        )
        ticket_service.type_registry.register(
            ApplyEventTeamTicket(
                senior_staff_role_id=senior_staff_role_id, application_service=self
            )
        )
        logger.info("Application ticket types registered")

    # -------------------------------------------------------------------------
    # Step-through flow
    # -------------------------------------------------------------------------

    async def start_application(
        self,
        *,
        type_id: str,
        channel: discord.TextChannel,
        ticket_id: int,
        applicant_id: int,
        guild_id: int,
    ) -> None:
        """Initialise a new application session and post the first question."""
        template = self._templates[type_id]
        response = SurveyResponse(
            ticket_id=ticket_id,
            template_id=type_id,
            respondent_id=applicant_id,
            guild_id=guild_id,
            channel_id=channel.id,
            started_at=datetime.now(UTC),
        )
        await self._repo.save_response(response)
        self._sessions[ticket_id] = response
        self._channels[ticket_id] = channel
        self._session_types[ticket_id] = type_id

        summary_msg = await self._post_summary_message(
            ticket_id, channel, template, response
        )
        response.summary_message_id = summary_msg.id
        self._summary_messages[ticket_id] = summary_msg
        await self._repo.update_response(ticket_id, summary_message_id=summary_msg.id)

        await self._post_next_question(ticket_id)
        logger.info(f"Application: started '{type_id}' flow for ticket #{ticket_id}")

    async def handle_answer(
        self,
        ticket_id: int,
        field_id: str,
        value: Any,
        interaction: discord.Interaction,
    ) -> None:
        """Record an answer and advance to the next field."""
        session = self._sessions.get(ticket_id)
        if not session:
            logger.warning(
                f"Application: handle_answer called for ticket #{ticket_id} "
                "but no session found"
            )
            return
        session.answers[field_id] = value
        session.current_field_index += 1
        await self._advance(ticket_id, interaction)

    async def skip_field(
        self,
        ticket_id: int,
        field_id: str,
        interaction: discord.Interaction,
    ) -> None:
        """Skip an optional field and advance to the next one."""
        session = self._sessions.get(ticket_id)
        if not session:
            return
        session.current_field_index += 1
        await self._advance(ticket_id, interaction)

    async def handle_submit(
        self, ticket_id: int, interaction: discord.Interaction
    ) -> None:
        """Mark the application as submitted and leave the ticket open for review."""
        session = self._sessions.get(ticket_id)
        channel = self._channels.get(ticket_id)
        now = datetime.now(UTC)

        if session:
            session.completed = True
            session.completed_at = now

        await self._repo.update_response(
            ticket_id, completed=True, completed_at=now.isoformat()
        )

        if channel:
            embed = discord.Embed(
                title="✅ Application Submitted!",
                description=(
                    "Your application has been received. "
                    "Staff will review it and get back to you here."
                ),
                color=discord.Color.green(),
            )
            await channel.send(embed=embed)

        self._sessions.pop(ticket_id, None)
        self._channels.pop(ticket_id, None)
        self._summary_messages.pop(ticket_id, None)
        self._question_messages.pop(ticket_id, None)
        self._session_types.pop(ticket_id, None)
        logger.info(
            f"Application: ticket #{ticket_id} submitted (left open for review)"
        )

    async def handle_discard(
        self, ticket_id: int, interaction: discord.Interaction
    ) -> None:
        """Discard the in-progress application and close the ticket."""
        self._question_messages.pop(ticket_id, None)
        self._sessions.pop(ticket_id, None)
        self._channels.pop(ticket_id, None)
        self._summary_messages.pop(ticket_id, None)
        self._session_types.pop(ticket_id, None)

        await self._repo.delete_response(ticket_id)

        if self._ticket_service:
            closer = interaction.user
            if isinstance(closer, discord.Member):
                await self._ticket_service.close_ticket(
                    ticket_id=ticket_id,
                    closer=closer,
                    reason="Application discarded.",
                    note=None,
                )
        logger.info(f"Application: ticket #{ticket_id} discarded by {interaction.user}")

    async def handle_reset(
        self, ticket_id: int, interaction: discord.Interaction
    ) -> None:
        """Clear all answers and restart the application from the first question."""
        session = self._sessions.get(ticket_id)
        type_id = self._session_types.get(ticket_id)
        if not session or not type_id:
            return

        session.answers = {}
        session.current_field_index = 0

        await self._repo.update_response(ticket_id, answers={}, current_field_index=0)

        question_msg = self._question_messages.pop(ticket_id, None)
        if question_msg:
            try:
                await question_msg.delete()
            except discord.NotFound:
                pass

        summary_msg = self._summary_messages.get(ticket_id)
        if summary_msg:
            template = self._templates[type_id]
            try:
                await summary_msg.edit(embed=build_summary_embed(template, session))
            except discord.NotFound:
                pass

        await self._post_next_question(ticket_id)
        logger.info(f"Application: ticket #{ticket_id} reset")

    async def restore_session(self, ticket_id: int, channel_id: int) -> None:
        """Restore a single in-progress session by ticket ID.

        Used when a ticket is reopened so the applicant can continue where
        they left off.
        """
        channel = self._guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                f"Application: cannot restore #{ticket_id}, "
                f"channel {channel_id} not found"
            )
            return

        response = await self._repo.get_response(ticket_id)
        if not response or response.completed:
            return

        type_id = response.template_id
        template = self._templates.get(type_id)
        if not template:
            logger.warning(
                f"Application: cannot restore #{ticket_id}, unknown type '{type_id}'"
            )
            return

        response.channel_id = channel_id
        await self._repo.update_response(ticket_id, channel_id=channel_id)

        self._sessions[ticket_id] = response
        self._channels[ticket_id] = channel
        self._session_types[ticket_id] = type_id
        await self._replace_summary_message(response, channel, template)
        await self._replace_question_message(response)
        logger.info(f"Application: restored session for ticket #{ticket_id}")

    async def restore_sessions(self) -> None:
        """Re-attach all in-progress sessions after a bot restart."""
        restored = 0
        for type_id, template in self._templates.items():
            responses = await self._repo.get_responses_for_template(
                self._guild.id, type_id
            )
            for response in responses:
                if response.completed or not response.channel_id:
                    continue
                channel = self._guild.get_channel(response.channel_id)
                if not isinstance(channel, discord.TextChannel):
                    continue
                self._sessions[response.ticket_id] = response
                self._channels[response.ticket_id] = channel
                self._session_types[response.ticket_id] = type_id
                await self._replace_summary_message(response, channel, template)
                await self._replace_question_message(response)
                restored += 1

        logger.info(f"Application: restored {restored} in-progress session(s)")

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _post_summary_message(
        self,
        ticket_id: int,
        channel: discord.TextChannel,
        template: SurveyTemplate,
        response: SurveyResponse,
    ) -> discord.Message:
        from features.tickets.application_views import ApplicationResetView

        return await channel.send(
            embed=build_summary_embed(template, response),
            view=ApplicationResetView(self, ticket_id),
        )

    async def _replace_summary_message(
        self,
        response: SurveyResponse,
        channel: discord.TextChannel,
        template: SurveyTemplate,
    ) -> None:
        """Delete the old summary message and post a fresh one with a new ResetView."""
        if response.summary_message_id:
            try:
                old = await channel.fetch_message(response.summary_message_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        msg = await self._post_summary_message(
            response.ticket_id, channel, template, response
        )
        response.summary_message_id = msg.id
        self._summary_messages[response.ticket_id] = msg
        await self._repo.update_response(response.ticket_id, summary_message_id=msg.id)

    async def _replace_question_message(self, response: SurveyResponse) -> None:
        """Delete the stale question message and re-post the current question."""
        channel = self._channels.get(response.ticket_id)
        if not channel:
            return
        if response.question_message_id:
            try:
                old = await channel.fetch_message(response.question_message_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        await self._post_next_question(response.ticket_id)

    async def _advance(self, ticket_id: int, interaction: discord.Interaction) -> None:
        session = self._sessions.get(ticket_id)
        type_id = self._session_types.get(ticket_id)
        channel = self._channels.get(ticket_id)
        if not session or not type_id or not channel:
            return

        template = self._templates[type_id]

        await self._repo.update_response(
            ticket_id,
            answers=session.answers,
            current_field_index=session.current_field_index,
        )

        question_msg = self._question_messages.pop(ticket_id, None)
        if question_msg:
            try:
                await question_msg.delete()
            except discord.NotFound:
                pass

        summary_msg = self._summary_messages.get(ticket_id)
        if summary_msg:
            try:
                await summary_msg.edit(embed=build_summary_embed(template, session))
            except discord.NotFound:
                pass

        if session.current_field_index >= len(template.fields):
            await self._post_completion(ticket_id, channel)
        else:
            await self._post_next_question(ticket_id)

    async def _post_next_question(self, ticket_id: int) -> None:
        session = self._sessions.get(ticket_id)
        type_id = self._session_types.get(ticket_id)
        channel = self._channels.get(ticket_id)
        if not session or not type_id or not channel:
            return

        template = self._templates[type_id]
        field = template.fields[session.current_field_index]
        total = len(template.fields)

        from features.survey.views.step_views import (
            SelectAnswerView,
            TextAnswerView,
            YesNoView,
            build_field_embed,
        )

        embed = build_field_embed(field, session.current_field_index, total)

        if field.type == "yes_no":
            view: discord.ui.View = YesNoView(self, ticket_id, field)
        elif field.type in ("short_text", "long_text"):
            view = TextAnswerView(self, ticket_id, field)
        else:
            view = SelectAnswerView(self, ticket_id, field)

        msg = await channel.send(embed=embed, view=view)
        self._question_messages[ticket_id] = msg
        session.question_message_id = msg.id

    async def _post_completion(
        self, ticket_id: int, channel: discord.TextChannel
    ) -> None:
        from features.tickets.application_views import ApplicationCompleteView

        embed = discord.Embed(
            title="✅ All questions answered!",
            description="Click **Submit Application** to finalise your responses.",
            color=discord.Color.green(),
        )
        view = ApplicationCompleteView(self, ticket_id)
        await channel.send(embed=embed, view=view)

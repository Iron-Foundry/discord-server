from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord
from loguru import logger

from common.ticket_types import TicketTypeId
from core.service_base import Service
from survey.models import ActiveSurvey, SurveyResponse, SurveyTemplate
from survey.repository import MongoSurveyRepository

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService


class SurveyService(Service):
    """Manages survey templates, active state, and the step-through response flow."""

    def __init__(
        self,
        guild: discord.Guild,
        client: discord.Client,
        repo: MongoSurveyRepository,
    ) -> None:
        self._guild = guild
        self._client = client
        self._repo = repo

        # Injected after construction in load_all_services
        self._ticket_service: "TicketService | None" = None

        # Cached active template
        self._current_template: SurveyTemplate | None = None

        # Per-ticket in-memory session state (cleared on ticket close)
        self._sessions: dict[int, SurveyResponse] = {}
        self._channels: dict[int, discord.TextChannel] = {}
        self._summary_messages: dict[int, discord.Message] = {}
        self._question_messages: dict[int, discord.Message] = {}

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def initialize(self) -> None:
        await self._repo.ensure_indexes()
        active = await self._repo.get_active(self._guild.id)
        if active:
            template = await self._repo.get_template(self._guild.id, active.template_id)
            self._current_template = template
            if template:
                logger.info(
                    f"Survey: loaded active template '{template.template_id}' on startup"
                )

    def set_ticket_service(
        self, ticket_service: "TicketService", staff_role_id: int
    ) -> None:
        """Wire up TicketService and register the SurveyTicket type.

        Called from load_all_services after all services are initialised.
        The survey type is registered disabled; it is enabled when a template
        is activated via ``/survey activate``.
        """
        from survey.ticket_type import SurveyTicket

        self._ticket_service = ticket_service
        ticket_type = SurveyTicket(staff_role_id=staff_role_id, survey_service=self)
        ticket_service.type_registry.register(ticket_type)

        if self._current_template:
            # A template was active before restart — keep the type enabled
            logger.info(
                "Survey: re-enabling ticket type (active template found on startup)"
            )
        else:
            ticket_service.type_registry.disable(TicketTypeId.SURVEY.value)

    # -------------------------------------------------------------------------
    # Template management
    # -------------------------------------------------------------------------

    @property
    def current_template(self) -> SurveyTemplate | None:
        return self._current_template

    async def save_template(self, template: SurveyTemplate) -> None:
        await self._repo.save_template(template)

    async def get_template(self, template_id: str) -> SurveyTemplate | None:
        return await self._repo.get_template(self._guild.id, template_id)

    async def list_templates(self) -> list[SurveyTemplate]:
        return await self._repo.list_templates(self._guild.id)

    async def delete_template(self, template_id: str) -> None:
        await self._repo.delete_template(self._guild.id, template_id)

    async def is_active_template(self, template_id: str) -> bool:
        active = await self._repo.get_active(self._guild.id)
        return active is not None and active.template_id == template_id

    # -------------------------------------------------------------------------
    # Activation
    # -------------------------------------------------------------------------

    async def activate(self, template_id: str, user_id: int) -> SurveyTemplate | None:
        """Set the active survey template. Returns the template or None if not found."""
        template = await self._repo.get_template(self._guild.id, template_id)
        if not template:
            return None
        active = ActiveSurvey(
            guild_id=self._guild.id,
            template_id=template_id,
            activated_by_id=user_id,
            activated_at=datetime.now(UTC),
        )
        await self._repo.set_active(active)
        self._current_template = template
        if self._ticket_service:
            await self._ticket_service.enable_type(TicketTypeId.SURVEY.value)
        logger.info(f"Survey: activated template '{template_id}'")
        return template

    async def deactivate(self) -> None:
        """Clear the active survey and disable the ticket type."""
        await self._repo.clear_active(self._guild.id)
        self._current_template = None
        if self._ticket_service:
            await self._ticket_service.disable_type(TicketTypeId.SURVEY.value)
        logger.info("Survey: deactivated")

    async def get_active_info(self) -> tuple[ActiveSurvey | None, int]:
        """Return (ActiveSurvey | None, response_count)."""
        active = await self._repo.get_active(self._guild.id)
        if not active:
            return None, 0
        responses = await self._repo.get_responses_for_template(
            self._guild.id, active.template_id
        )
        return active, len(responses)

    # -------------------------------------------------------------------------
    # Response queries
    # -------------------------------------------------------------------------

    async def get_responses(
        self, template_id: str | None = None
    ) -> list[SurveyResponse]:
        tid = template_id or (
            self._current_template.template_id if self._current_template else None
        )
        if not tid:
            return []
        return await self._repo.get_responses_for_template(self._guild.id, tid)

    async def get_response(self, ticket_id: int) -> SurveyResponse | None:
        return await self._repo.get_response(ticket_id)

    async def delete_responses(self, template_id: str) -> int:
        return await self._repo.delete_responses_for_template(
            self._guild.id, template_id
        )

    # -------------------------------------------------------------------------
    # Survey step-through flow
    # -------------------------------------------------------------------------

    async def start_survey(
        self,
        *,
        channel: discord.TextChannel,
        ticket_id: int,
        respondent_id: int,
        guild_id: int,
    ) -> None:
        """Initialise a new survey session and post the first question."""
        template = self._current_template
        if not template:
            await channel.send(
                "⚠️ No active survey template found. Please contact staff."
            )
            logger.warning(
                f"Survey: start_survey called for ticket #{ticket_id} but no template is active"
            )
            return

        response = SurveyResponse(
            ticket_id=ticket_id,
            template_id=template.template_id,
            respondent_id=respondent_id,
            guild_id=guild_id,
            started_at=datetime.now(UTC),
        )
        await self._repo.save_response(response)
        self._sessions[ticket_id] = response
        self._channels[ticket_id] = channel

        # Post persistent running-summary embed
        from survey.views.summary_view import build_summary_embed

        summary_msg = await channel.send(embed=build_summary_embed(template, response))
        response.summary_message_id = summary_msg.id
        self._summary_messages[ticket_id] = summary_msg
        await self._repo.update_response(ticket_id, summary_message_id=summary_msg.id)

        await self._post_next_question(ticket_id)
        logger.info(
            f"Survey: started for ticket #{ticket_id} (template '{template.template_id}')"
        )

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
                f"Survey: handle_answer called for ticket #{ticket_id} but no session found"
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
        """Mark the survey as complete and auto-close the ticket."""
        session = self._sessions.get(ticket_id)
        now = datetime.now(UTC)

        if session:
            session.completed = True
            session.completed_at = now

        await self._repo.update_response(
            ticket_id, completed=True, completed_at=now.isoformat()
        )

        # Clean up in-memory state
        self._sessions.pop(ticket_id, None)
        self._channels.pop(ticket_id, None)
        self._summary_messages.pop(ticket_id, None)
        self._question_messages.pop(ticket_id, None)

        if self._ticket_service:
            bot_member = self._guild.me
            if bot_member:
                await self._ticket_service.close_ticket(
                    ticket_id=ticket_id,
                    closer=bot_member,
                    reason="Survey completed — thank you for your response!",
                    note=None,
                )
            else:
                logger.error(
                    f"Survey: guild.me is None, cannot auto-close ticket #{ticket_id}"
                )
        logger.info(f"Survey: ticket #{ticket_id} submitted and closed")

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _advance(self, ticket_id: int, interaction: discord.Interaction) -> None:
        session = self._sessions.get(ticket_id)
        template = self._current_template
        channel = self._channels.get(ticket_id)
        if not session or not template or not channel:
            return

        # Persist current answer + index
        await self._repo.update_response(
            ticket_id,
            answers=session.answers,
            current_field_index=session.current_field_index,
        )

        # Delete the answered question message
        question_msg = self._question_messages.pop(ticket_id, None)
        if question_msg:
            try:
                await question_msg.delete()
            except discord.NotFound:
                pass

        # Edit the running summary
        summary_msg = self._summary_messages.get(ticket_id)
        if summary_msg:
            from survey.views.summary_view import build_summary_embed

            try:
                await summary_msg.edit(embed=build_summary_embed(template, session))
            except discord.NotFound:
                pass

        # Advance to next field or completion
        if session.current_field_index >= len(template.fields):
            await self._post_completion(ticket_id, channel)
        else:
            await self._post_next_question(ticket_id)

    async def _post_next_question(self, ticket_id: int) -> None:
        session = self._sessions.get(ticket_id)
        template = self._current_template
        channel = self._channels.get(ticket_id)
        if not session or not template or not channel:
            return

        field = template.fields[session.current_field_index]
        total = len(template.fields)

        from survey.views.step_views import (
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
        from survey.views.summary_view import SurveyCompleteView

        embed = discord.Embed(
            title="✅ All questions answered!",
            description=(
                "Click **Submit Survey** to finalise your responses. "
                "Your ticket will close automatically."
            ),
            color=discord.Color.green(),
        )
        view = SurveyCompleteView(self, ticket_id)
        await channel.send(embed=embed, view=view)

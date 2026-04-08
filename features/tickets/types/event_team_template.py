from datetime import UTC, datetime

from core.common.ticket_types import TicketTypeId
from features.survey.models import SurveyField, SurveyTemplate


def build_event_team_template(guild_id: int) -> SurveyTemplate:
    """Return the application template for the event team role."""
    return SurveyTemplate(
        template_id=TicketTypeId.APPLY_EVENT_TEAM.value,
        guild_id=guild_id,
        title="Event Team Application",
        description="Apply to join the Iron Foundry event team.",
        fields=[
            # ── Basic Information ─────────────────────────────────────────────
            SurveyField(
                id="timezone",
                type="short_text",
                label="What is your time zone?",
                required=True,
            ),
            SurveyField(
                id="hours_per_week",
                type="short_text",
                label="How many hours per week do you actively play OSRS?",
                required=True,
            ),
            SurveyField(
                id="discord_activity",
                type="short_text",
                label="How often are you on, or check Discord?",
                required=True,
            ),
            SurveyField(
                id="past_events",
                type="long_text",
                label="What events have you been a part of?",
                description="At Iron Foundry, or any other clan.",
                required=True,
            ),
            SurveyField(
                id="hosting_experience",
                type="long_text",
                label="Do you have any prior experience hosting events?",
                required=True,
            ),
            SurveyField(
                id="low_attendance",
                type="long_text",
                label="How would you handle low attendance at an event?",
                required=True,
            ),
            SurveyField(
                id="feedback_response",
                type="long_text",
                label="How do you respond to feedback or criticism?",
                required=True,
            ),
            SurveyField(
                id="teamwork",
                type="yes_no",
                label="Are you comfortable working within a team environment?",
                required=True,
            ),
            SurveyField(
                id="areas_of_interest",
                type="select",
                label="Which areas are you most interested in?",
                description="Select all that apply.",
                options=[
                    "Community Events (e.g. movie nights, social activities)",
                    "Quick Events (e.g. hide & seek, skilling trips)",
                    "Large-Scale Events (e.g. bingo, frenzies)",
                    "Recurring Events (e.g. BOTW, SOTW, ROTW, Callisto trips)",
                ],
                max_choices=4,
                required=True,
            ),
            SurveyField(
                id="community_discord_activity",
                type="long_text",
                label="How would you encourage Discord activity with your events?",
                description=(
                    "Community Events Manager interest — skip if not applicable."
                ),
                required=False,
            ),
            SurveyField(
                id="community_ideas",
                type="long_text",
                label="What ideas would you bring to the community?",
                description=(
                    "Community Events Manager interest — skip if not applicable."
                ),
                required=False,
            ),
            SurveyField(
                id="hosting_frequency",
                type="short_text",
                label="How frequently would you aim to host?",
                description=(
                    "Community Events Manager interest — skip if not applicable."
                ),
                required=False,
            ),
        ],
        created_at=datetime.now(UTC),
        created_by_id=0,
    )

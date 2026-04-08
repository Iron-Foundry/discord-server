from datetime import UTC, datetime

from core.common.ticket_types import TicketTypeId
from features.survey.models import SurveyField, SurveyTemplate


def build_mentor_template(guild_id: int) -> SurveyTemplate:
    """Return the application template for the mentor role."""
    return SurveyTemplate(
        template_id=TicketTypeId.APPLY_MENTOR.value,
        guild_id=guild_id,
        title="Mentor Application",
        description="Apply to become a mentor for the Iron Foundry clan.",
        fields=[
            SurveyField(
                id="rsn",
                type="short_text",
                label="RuneScape Name (RSN)",
                description="Your exact in-game name.",
                required=True,
            ),
            SurveyField(
                id="experience",
                type="long_text",
                label="OSRS Experience",
                description=(
                    "e.g. 2000 total level, maxed combat, "
                    "end-game PvM content completed."
                ),
                required=True,
            ),
            SurveyField(
                id="reason",
                type="long_text",
                label="Why do you want to be a mentor?",
                description=(
                    "Describe how you would help members learn and what "
                    "content you would want to mentor for."
                ),
                required=True,
            ),
        ],
        created_at=datetime.now(UTC),
        created_by_id=0,
    )

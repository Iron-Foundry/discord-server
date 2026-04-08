from datetime import UTC, datetime

from core.common.ticket_types import TicketTypeId
from features.survey.models import SurveyField, SurveyTemplate


def build_staff_template(guild_id: int) -> SurveyTemplate:
    """Return the application template for the staff/moderator role."""
    return SurveyTemplate(
        template_id=TicketTypeId.APPLY_STAFF.value,
        guild_id=guild_id,
        title="Staff Application",
        description="Apply to join the Iron Foundry staff team.",
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
                label="How active are you on Discord?",
                description="e.g. daily, a few times a week, weekends only.",
                required=True,
            ),
            # ── Experience & Knowledge ────────────────────────────────────────
            SurveyField(
                id="osrs_experience",
                type="long_text",
                label="How experienced would you consider yourself in OSRS?",
                required=True,
            ),
            SurveyField(
                id="mod_experience",
                type="long_text",
                label="Do you have any prior moderation or leadership experience?",
                description="In any game or community.",
                required=True,
            ),
            SurveyField(
                id="discord_knowledge",
                type="short_text",
                label="How familiar are you with Discord moderation tools and features?",
                required=True,
            ),
            # ── Skills & Approach ─────────────────────────────────────────────
            SurveyField(
                id="conflict_handling",
                type="long_text",
                label="How would you handle a conflict between members?",
                description="In-game or on Discord.",
                required=True,
            ),
            SurveyField(
                id="deescalation",
                type="yes_no",
                label=(
                    "Are you comfortable stepping in to de-escalate "
                    "tense or inappropriate situations?"
                ),
                required=True,
            ),
            SurveyField(
                id="rule_enforcement",
                type="long_text",
                label="How would you ensure fairness and consistency when enforcing rules?",
                required=True,
            ),
            SurveyField(
                id="teamwork",
                type="yes_no",
                label="Do you feel confident working as part of a team?",
                required=True,
            ),
            # ── Clan Insight ──────────────────────────────────────────────────
            SurveyField(
                id="clan_like",
                type="long_text",
                label="What do you like most about Iron Foundry?",
                required=True,
            ),
            SurveyField(
                id="clan_improve",
                type="long_text",
                label="What, if anything, would you improve within the clan?",
                required=False,
            ),
            SurveyField(
                id="great_mod",
                type="long_text",
                label="What do you think makes a great moderator in our community?",
                required=True,
            ),
            # ── Role Interest ─────────────────────────────────────────────────
            SurveyField(
                id="role_interest",
                type="select",
                label="Which areas are you most interested in contributing to?",
                description="Select all that apply.",
                options=[
                    "Recruitment",
                    "Socials & Calendar Management",
                    "Mentorship (Dragonstone+)",
                    "Events",
                    "Tickets & Support",
                ],
                max_choices=5,
                required=True,
            ),
        ],
        created_at=datetime.now(UTC),
        created_by_id=0,
    )

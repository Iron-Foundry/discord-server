from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from features.survey.models import SurveyResponse, SurveyTemplate

if TYPE_CHECKING:
    from features.survey.service import SurveyService


class SurveyResetView(discord.ui.View):
    """Persistent controls attached to the running summary message."""

    def __init__(self, service: "SurveyService", ticket_id: int) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def reset_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.defer()
        await self._service.handle_reset(self._ticket_id, interaction)

    @discord.ui.button(label="Discard", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def discard_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.defer()
        self.stop()
        await self._service.handle_discard(self._ticket_id, interaction)


def build_summary_embed(
    template: SurveyTemplate,
    response: SurveyResponse,
) -> discord.Embed:
    """Build the running-summary embed that is edited after each answer."""
    answered = len(response.answers)
    total = len(template.fields)

    embed = discord.Embed(
        title=f"📋 {template.title}",
        description=template.description,
        color=discord.Color.blurple(),
    )

    for field in template.fields:
        value = response.answers.get(field.id)
        if value is None:
            display = "*Not yet answered*"
        elif isinstance(value, bool):
            display = "✅ Yes" if value else "❌ No"
        elif isinstance(value, list):
            display = ", ".join(str(v) for v in value)
        else:
            text = str(value)
            display = text[:1021] + "..." if len(text) > 1024 else text

        embed.add_field(name=field.label, value=display, inline=False)

    embed.set_footer(text=f"{answered}/{total} fields answered")
    return embed


class SurveyCompleteView(discord.ui.View):
    """Posted after all fields are answered; prompts the user to submit."""

    def __init__(self, service: "SurveyService", ticket_id: int) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id

    @discord.ui.button(
        label="Submit Survey", style=discord.ButtonStyle.success, emoji="📨"
    )
    async def submit_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.defer()
        self.stop()
        await self._service.handle_submit(self._ticket_id, interaction)

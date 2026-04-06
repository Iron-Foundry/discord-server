from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from survey.models import SurveyField

if TYPE_CHECKING:
    from survey.service import SurveyService


def build_field_embed(field: SurveyField, index: int, total: int) -> discord.Embed:
    type_labels = {
        "yes_no": "Yes / No",
        "short_text": "Short Text",
        "long_text": "Long Text",
        "select": "Select",
    }
    badge = type_labels.get(field.type, field.type)
    required_text = "Required" if field.required else "Optional"

    embed = discord.Embed(
        title=field.label,
        description=field.description,
        color=discord.Color.blurple(),
    )
    embed.set_footer(
        text=f"Question {index + 1} of {total}  •  {badge}  •  {required_text}"
    )
    return embed


class SkipButton(discord.ui.Button):  # type: ignore[type-arg]
    def __init__(self, service: "SurveyService", ticket_id: int, field_id: str) -> None:
        super().__init__(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
        self._service = service
        self._ticket_id = ticket_id
        self._field_id = field_id

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.view:
            self.view.stop()
        await self._service.skip_field(self._ticket_id, self._field_id, interaction)


class YesNoView(discord.ui.View):
    def __init__(
        self, service: "SurveyService", ticket_id: int, field: SurveyField
    ) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id
        self._field = field

        if not field.required:
            self.add_item(SkipButton(service, ticket_id, field.id))

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.defer()
        self.stop()
        await self._service.handle_answer(
            self._ticket_id, self._field.id, True, interaction
        )

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger, emoji="❌")
    async def no_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.defer()
        self.stop()
        await self._service.handle_answer(
            self._ticket_id, self._field.id, False, interaction
        )


class SingleFieldModal(discord.ui.Modal):
    def __init__(
        self,
        service: "SurveyService",
        ticket_id: int,
        field: SurveyField,
        style: discord.TextStyle,
    ) -> None:
        super().__init__(title=field.label[:45])
        self._service = service
        self._ticket_id = ticket_id
        self._field_id = field.id

        max_length = 4000 if style == discord.TextStyle.paragraph else 1024
        self._input = discord.ui.TextInput(
            label=field.label[:45],
            placeholder=field.description
            or (
                "Enter a detailed response..."
                if style == discord.TextStyle.paragraph
                else "Enter your response..."
            ),
            style=style,
            required=True,
            max_length=max_length,
        )
        self.add_item(self._input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self._service.handle_answer(
            self._ticket_id, self._field_id, self._input.value, interaction
        )


class TextAnswerView(discord.ui.View):
    def __init__(
        self, service: "SurveyService", ticket_id: int, field: SurveyField
    ) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id
        self._field = field

        if not field.required:
            self.add_item(SkipButton(service, ticket_id, field.id))

    @discord.ui.button(label="Answer", style=discord.ButtonStyle.primary, emoji="✏️")
    async def answer_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        style = (
            discord.TextStyle.paragraph
            if self._field.type == "long_text"
            else discord.TextStyle.short
        )
        modal = SingleFieldModal(self._service, self._ticket_id, self._field, style)
        await interaction.response.send_modal(modal)


class FieldSelect(discord.ui.Select):  # type: ignore[type-arg]
    def __init__(
        self, service: "SurveyService", ticket_id: int, field: SurveyField
    ) -> None:
        self._service = service
        self._ticket_id = ticket_id
        self._field = field
        options = [discord.SelectOption(label=opt) for opt in field.options]
        max_v = min(field.max_choices, len(field.options))
        placeholder = (
            f"Choose up to {field.max_choices} option(s)..."
            if field.max_choices > 1
            else "Choose an option..."
        )
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=max_v,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        value: list[str] | str = (
            self.values if self._field.max_choices > 1 else self.values[0]
        )
        if self.view:
            self.view.stop()
        await self._service.handle_answer(
            self._ticket_id, self._field.id, value, interaction
        )


class SelectAnswerView(discord.ui.View):
    def __init__(
        self, service: "SurveyService", ticket_id: int, field: SurveyField
    ) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id
        self._field = field

        self.add_item(FieldSelect(service, ticket_id, field))

        if not field.required:
            self.add_item(SkipButton(service, ticket_id, field.id))

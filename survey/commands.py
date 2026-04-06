from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from command_infra.checks import handle_check_failure, is_senior_staff, is_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry
from survey.charts import generate_summary_charts
from survey.models import SurveyTemplate
from survey.toml_io import EXAMPLE_TOML, SurveyValidationError, export_toml, parse_toml

if TYPE_CHECKING:
    from survey.service import SurveyService


# ---------------------------------------------------------------------------
# Help registration
# ---------------------------------------------------------------------------


def register_help(registry: HelpRegistry) -> None:
    registry.add_group(
        HelpGroup(
            name="survey",
            description="Manage survey templates and view responses",
            commands=[
                HelpEntry(
                    "/survey template example",
                    "Download a fully-annotated example TOML template",
                    "Staff",
                ),
                HelpEntry(
                    "/survey template import <name> <attachment>",
                    "Import a TOML template file and save it under the given name",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/survey template export <name>",
                    "Download a template as a TOML file",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/survey template replace <name> <attachment>",
                    "Replace an existing template with a new TOML file",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/survey template list",
                    "List all saved survey templates",
                    "Staff",
                ),
                HelpEntry(
                    "/survey template show <name>",
                    "Show the fields of a template in detail",
                    "Staff",
                ),
                HelpEntry(
                    "/survey template delete <name>",
                    "Delete a template (blocked if currently active)",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/survey activate <template>",
                    "Set the active survey (enables the survey ticket type)",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/survey deactivate",
                    "Deactivate the current survey (disables the survey ticket type)",
                    "Senior Staff",
                ),
                HelpEntry("/survey status", "Show the currently active survey", "Staff"),
                HelpEntry(
                    "/survey responses list [template]",
                    "List respondents and completion status",
                    "Staff",
                ),
                HelpEntry(
                    "/survey responses view <ticket_id>",
                    "View a single response in full",
                    "Staff",
                ),
                HelpEntry(
                    "/survey responses export [template]",
                    "Download all responses as a CSV file",
                    "Staff",
                ),
                HelpEntry(
                    "/survey responses summary [template]",
                    "Aggregated stats and per-field charts",
                    "Staff",
                ),
                HelpEntry(
                    "/survey responses clear <template>",
                    "Delete all responses for a template (with confirmation)",
                    "Senior Staff",
                ),
            ],
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return discord.utils.format_dt(dt, style="f")


async def _template_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    service: SurveyService = interaction.client.survey_service  # type: ignore[attr-defined]
    templates = await service.list_templates()
    return [
        app_commands.Choice(name=t.template_id, value=t.template_id)
        for t in templates
        if current.lower() in t.template_id.lower()
    ][:25]


def _build_template_list_embed(templates: list[SurveyTemplate]) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Survey Templates",
        color=discord.Color.blurple(),
    )
    if not templates:
        embed.description = "*No templates saved yet.*"
        return embed
    for t in templates:
        value = f"{len(t.fields)} fields"
        if t.description:
            value += f"\n{t.description[:80]}"
        embed.add_field(name=t.template_id, value=value, inline=False)
    return embed


def _build_template_detail_embed(template: SurveyTemplate) -> discord.Embed:
    type_icons = {
        "yes_no": "🔘",
        "short_text": "💬",
        "long_text": "📝",
        "select": "🔽",
    }
    embed = discord.Embed(
        title=f"📋 {template.title}",
        description=template.description,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"ID: {template.template_id}")
    for i, field in enumerate(template.fields, 1):
        icon = type_icons.get(field.type, "•")
        req = "Required" if field.required else "Optional"
        lines = [f"`{field.type}`  •  {req}"]
        if field.description:
            lines.append(field.description)
        if field.type == "select":
            opts = ", ".join(f"`{o}`" for o in field.options)
            lines.append(f"Options: {opts}")
            if field.max_choices > 1:
                lines.append(f"Max choices: {field.max_choices}")
        embed.add_field(
            name=f"{icon} {i}. {field.label}", value="\n".join(lines), inline=False
        )
    return embed


def _build_response_csv(template: SurveyTemplate, responses: list) -> bytes:
    buf = io.StringIO()
    field_ids = [f.id for f in template.fields]
    headers = ["ticket_id", "respondent_id", "started_at", "completed_at", "completed"]
    headers += field_ids
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in responses:
        row = [
            r.ticket_id,
            r.respondent_id,
            r.started_at.isoformat() if r.started_at else "",
            r.completed_at.isoformat() if r.completed_at else "",
            r.completed,
        ]
        for fid in field_ids:
            val = r.answers.get(fid, "")
            if isinstance(val, list):
                val = "; ".join(val)
            elif isinstance(val, bool):
                val = "Yes" if val else "No"
            row.append(val)
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Confirm-delete view
# ---------------------------------------------------------------------------


class _ConfirmDeleteView(discord.ui.View):
    def __init__(self, service: "SurveyService", template_id: str) -> None:
        super().__init__(timeout=60)
        self._service = service
        self._template_id = template_id

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button  # type: ignore[type-arg]
    ) -> None:
        await self._service.delete_template(self._template_id)
        await interaction.response.edit_message(
            content=f"Template `{self._template_id}` has been deleted.", view=None
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


class _ConfirmClearView(discord.ui.View):
    def __init__(self, service: "SurveyService", template_id: str) -> None:
        super().__init__(timeout=60)
        self._service = service
        self._template_id = template_id

    @discord.ui.button(label="Confirm Clear", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button  # type: ignore[type-arg]
    ) -> None:
        count = await self._service.delete_responses(self._template_id)
        await interaction.response.edit_message(
            content=f"Deleted **{count}** response(s) for `{self._template_id}`.",
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)
        self.stop()


# ---------------------------------------------------------------------------
# /survey template <subcommand>
# ---------------------------------------------------------------------------


class TemplateSubgroup(app_commands.Group):
    def __init__(self, service: "SurveyService") -> None:
        super().__init__(name="template", description="Manage survey templates")
        self._service = service

    # /survey template example
    @app_commands.command(
        name="example",
        description="Download a fully-annotated example TOML template",
    )
    @is_staff()
    async def example_template(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        file = discord.File(
            io.BytesIO(EXAMPLE_TOML.encode("utf-8")),
            filename="example_survey.toml",
        )
        await interaction.followup.send(
            "Here's a complete example covering all four field types. "
            "Edit it, then use `/survey template import` to save it.",
            file=file,
            ephemeral=True,
        )

    # /survey template import
    @app_commands.command(name="import", description="Import a TOML template file")
    @app_commands.describe(
        name="Unique slug for this template (e.g. monthly_feedback)",
        attachment="TOML file to import",
    )
    @is_senior_staff()
    async def import_template(
        self,
        interaction: discord.Interaction,
        name: str,
        attachment: discord.Attachment,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not attachment.filename.endswith(".toml"):
            await interaction.followup.send(
                "Please attach a `.toml` file.", ephemeral=True
            )
            return
        data = await attachment.read()
        try:
            template = parse_toml(
                data,
                name=name,
                guild_id=interaction.guild_id or 0,
                created_by_id=interaction.user.id,
            )
        except SurveyValidationError as exc:
            await interaction.followup.send(
                f"**Invalid template:**\n{exc}", ephemeral=True
            )
            return
        await self._service.save_template(template)
        await interaction.followup.send(
            f"✅ Template `{name}` saved with **{len(template.fields)}** field(s).",
            ephemeral=True,
        )

    # /survey template export
    @app_commands.command(name="export", description="Download a template as a TOML file")
    @app_commands.describe(name="Template to export")
    @app_commands.autocomplete(name=_template_autocomplete)
    @is_senior_staff()
    async def export_template(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        template = await self._service.get_template(name)
        if not template:
            await interaction.followup.send(
                f"Template `{name}` not found.", ephemeral=True
            )
            return
        data = export_toml(template)
        file = discord.File(io.BytesIO(data), filename=f"{name}.toml")
        await interaction.followup.send(file=file, ephemeral=True)

    # /survey template replace
    @app_commands.command(name="replace", description="Replace an existing template with a new TOML file")
    @app_commands.describe(
        name="Template to replace",
        attachment="New TOML file",
    )
    @app_commands.autocomplete(name=_template_autocomplete)
    @is_senior_staff()
    async def replace_template(
        self,
        interaction: discord.Interaction,
        name: str,
        attachment: discord.Attachment,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = await self._service.get_template(name)
        if not existing:
            await interaction.followup.send(
                f"Template `{name}` not found. Use `/survey template import` to create it.",
                ephemeral=True,
            )
            return
        if not attachment.filename.endswith(".toml"):
            await interaction.followup.send(
                "Please attach a `.toml` file.", ephemeral=True
            )
            return
        data = await attachment.read()
        try:
            template = parse_toml(
                data,
                name=name,
                guild_id=interaction.guild_id or 0,
                created_by_id=interaction.user.id,
            )
        except SurveyValidationError as exc:
            await interaction.followup.send(
                f"**Invalid template:**\n{exc}", ephemeral=True
            )
            return
        await self._service.save_template(template)
        await interaction.followup.send(
            f"✅ Template `{name}` replaced with **{len(template.fields)}** field(s).",
            ephemeral=True,
        )

    # /survey template list
    @app_commands.command(name="list", description="List all saved survey templates")
    @is_staff()
    async def list_templates(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        templates = await self._service.list_templates()
        await interaction.followup.send(
            embed=_build_template_list_embed(templates), ephemeral=True
        )

    # /survey template show
    @app_commands.command(name="show", description="Show template fields in detail")
    @app_commands.describe(name="Template to inspect")
    @app_commands.autocomplete(name=_template_autocomplete)
    @is_staff()
    async def show_template(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        template = await self._service.get_template(name)
        if not template:
            await interaction.followup.send(
                f"Template `{name}` not found.", ephemeral=True
            )
            return
        await interaction.followup.send(
            embed=_build_template_detail_embed(template), ephemeral=True
        )

    # /survey template delete
    @app_commands.command(name="delete", description="Delete a saved template")
    @app_commands.describe(name="Template to delete")
    @app_commands.autocomplete(name=_template_autocomplete)
    @is_senior_staff()
    async def delete_template(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        template = await self._service.get_template(name)
        if not template:
            await interaction.followup.send(
                f"Template `{name}` not found.", ephemeral=True
            )
            return
        if await self._service.is_active_template(name):
            await interaction.followup.send(
                f"Template `{name}` is currently active. Run `/survey deactivate` first.",
                ephemeral=True,
            )
            return
        view = _ConfirmDeleteView(self._service, name)
        await interaction.followup.send(
            f"Delete template `{name}` ({len(template.fields)} fields)? This cannot be undone.",
            view=view,
            ephemeral=True,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)


# ---------------------------------------------------------------------------
# /survey responses <subcommand>
# ---------------------------------------------------------------------------


class ResponsesSubgroup(app_commands.Group):
    def __init__(self, service: "SurveyService") -> None:
        super().__init__(name="responses", description="View and export survey responses")
        self._service = service

    async def _resolve_template(
        self, template_id: str | None
    ) -> SurveyTemplate | None:
        if template_id:
            return await self._service.get_template(template_id)
        return self._service.current_template

    # /survey responses list
    @app_commands.command(name="list", description="List respondents and completion status")
    @app_commands.describe(template="Template to query (defaults to active)")
    @app_commands.autocomplete(template=_template_autocomplete)
    @is_staff()
    async def list_responses(
        self,
        interaction: discord.Interaction,
        template: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        tmpl = await self._resolve_template(template)
        if not tmpl:
            await interaction.followup.send(
                "No template specified and no active survey.", ephemeral=True
            )
            return
        responses = await self._service.get_responses(tmpl.template_id)
        embed = discord.Embed(
            title=f"📋 Responses — {tmpl.title}",
            color=discord.Color.blurple(),
        )
        if not responses:
            embed.description = "*No responses yet.*"
        else:
            completed = sum(1 for r in responses if r.completed)
            embed.description = (
                f"**{len(responses)}** total  •  **{completed}** completed"
            )
            lines: list[str] = []
            for r in responses[-25:]:  # Show most recent 25
                status = "✅" if r.completed else "🔄"
                answered = len(r.answers)
                total_fields = len(tmpl.fields)
                lines.append(
                    f"{status} `#{r.ticket_id:04d}` <@{r.respondent_id}> — "
                    f"{answered}/{total_fields} answered"
                )
            embed.add_field(
                name="Responses (most recent 25)", value="\n".join(lines), inline=False
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # /survey responses view
    @app_commands.command(name="view", description="View a single response in full")
    @app_commands.describe(ticket_id="Ticket ID of the response")
    @is_staff()
    async def view_response(
        self, interaction: discord.Interaction, ticket_id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        response = await self._service.get_response(ticket_id)
        if not response:
            await interaction.followup.send(
                f"No survey response found for ticket #{ticket_id}.", ephemeral=True
            )
            return
        template = await self._service.get_template(response.template_id)
        embed = discord.Embed(
            title=f"📋 Response — Ticket #{ticket_id:04d}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Respondent", value=f"<@{response.respondent_id}>", inline=True)
        embed.add_field(name="Template", value=response.template_id, inline=True)
        embed.add_field(
            name="Status",
            value="✅ Completed" if response.completed else "🔄 In progress",
            inline=True,
        )
        embed.add_field(name="Started", value=_fmt_dt(response.started_at), inline=True)
        if response.completed_at:
            embed.add_field(name="Completed", value=_fmt_dt(response.completed_at), inline=True)

        if template:
            for field in template.fields:
                val = response.answers.get(field.id)
                if val is None:
                    display = "*Skipped / not answered*"
                elif isinstance(val, bool):
                    display = "✅ Yes" if val else "❌ No"
                elif isinstance(val, list):
                    display = ", ".join(str(v) for v in val)
                else:
                    text = str(val)
                    display = text[:1021] + "..." if len(text) > 1024 else text
                embed.add_field(name=field.label, value=display, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # /survey responses export
    @app_commands.command(name="export", description="Download all responses as a CSV")
    @app_commands.describe(template="Template to export (defaults to active)")
    @app_commands.autocomplete(template=_template_autocomplete)
    @is_staff()
    async def export_responses(
        self,
        interaction: discord.Interaction,
        template: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        tmpl = await self._resolve_template(template)
        if not tmpl:
            await interaction.followup.send(
                "No template specified and no active survey.", ephemeral=True
            )
            return
        responses = await self._service.get_responses(tmpl.template_id)
        if not responses:
            await interaction.followup.send(
                f"No responses for `{tmpl.template_id}`.", ephemeral=True
            )
            return
        csv_bytes = _build_response_csv(tmpl, responses)
        filename = f"responses_{tmpl.template_id}_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
        file = discord.File(io.BytesIO(csv_bytes), filename=filename)
        await interaction.followup.send(
            f"**{len(responses)}** response(s) for `{tmpl.template_id}`.",
            file=file,
            ephemeral=True,
        )

    # /survey responses summary
    @app_commands.command(
        name="summary", description="Aggregated stats and per-field charts"
    )
    @app_commands.describe(template="Template to summarise (defaults to active)")
    @app_commands.autocomplete(template=_template_autocomplete)
    @is_staff()
    async def summary_responses(
        self,
        interaction: discord.Interaction,
        template: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        tmpl = await self._resolve_template(template)
        if not tmpl:
            await interaction.followup.send(
                "No template specified and no active survey.", ephemeral=True
            )
            return
        responses = await self._service.get_responses(tmpl.template_id)

        embed = discord.Embed(
            title=f"📊 Summary — {tmpl.title}",
            color=discord.Color.blurple(),
        )
        total = len(responses)
        completed = sum(1 for r in responses if r.completed)
        embed.add_field(name="Responses", value=str(total), inline=True)
        embed.add_field(name="Completed", value=str(completed), inline=True)
        embed.add_field(
            name="Completion rate",
            value=f"{completed / total * 100:.0f}%" if total else "—",
            inline=True,
        )

        # Text-field response counts
        for field in tmpl.fields:
            if field.type in ("short_text", "long_text"):
                answered = sum(1 for r in responses if field.id in r.answers)
                embed.add_field(
                    name=f"💬 {field.label}",
                    value=f"{answered}/{total} answered (see CSV export for text responses)",
                    inline=False,
                )

        if not responses:
            embed.description = "*No responses yet.*"
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Generate charts for yes_no / select fields
        charts = await generate_summary_charts(tmpl.fields, responses)
        files = [file for _, file in charts]

        await interaction.followup.send(embed=embed, files=files or [], ephemeral=True)

    # /survey responses clear
    @app_commands.command(name="clear", description="Delete all responses for a template")
    @app_commands.describe(template="Template whose responses to clear")
    @app_commands.autocomplete(template=_template_autocomplete)
    @is_senior_staff()
    async def clear_responses(
        self, interaction: discord.Interaction, template: str
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        tmpl = await self._service.get_template(template)
        if not tmpl:
            await interaction.followup.send(
                f"Template `{template}` not found.", ephemeral=True
            )
            return
        view = _ConfirmClearView(self._service, template)
        await interaction.followup.send(
            f"Delete **all** responses for `{template}`? This cannot be undone.",
            view=view,
            ephemeral=True,
        )

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)


# ---------------------------------------------------------------------------
# /survey (root group)
# ---------------------------------------------------------------------------


class SurveyGroup(app_commands.Group, name="survey", description="Survey management"):
    def __init__(self, service: "SurveyService") -> None:
        super().__init__()
        self._service = service
        self.add_command(TemplateSubgroup(service))
        self.add_command(ResponsesSubgroup(service))

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # /survey activate
    @app_commands.command(name="activate", description="Set the active survey")
    @app_commands.describe(template="Template to activate")
    @app_commands.autocomplete(template=_template_autocomplete)
    @is_senior_staff()
    async def activate(self, interaction: discord.Interaction, template: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await self._service.activate(template, interaction.user.id)
        if not result:
            await interaction.followup.send(
                f"Template `{template}` not found.", ephemeral=True
            )
            return
        await interaction.followup.send(
            f"✅ Survey **{result.title}** is now active. "
            "The survey ticket type has been enabled.",
            ephemeral=True,
        )
        logger.info(
            f"Survey: '{template}' activated by {interaction.user} (#{interaction.user.id})"
        )

    # /survey deactivate
    @app_commands.command(name="deactivate", description="Deactivate the current survey")
    @is_senior_staff()
    async def deactivate(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.deactivate()
        await interaction.followup.send(
            "Survey deactivated. The survey ticket type has been disabled.",
            ephemeral=True,
        )

    # /survey status
    @app_commands.command(name="status", description="Show the currently active survey")
    @is_staff()
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        active, count = await self._service.get_active_info()
        embed = discord.Embed(title="📋 Survey Status", color=discord.Color.blurple())
        if not active:
            embed.description = "*No active survey.*"
        else:
            template = await self._service.get_template(active.template_id)
            embed.add_field(name="Active template", value=active.template_id, inline=True)
            embed.add_field(
                name="Title",
                value=template.title if template else "—",
                inline=True,
            )
            embed.add_field(name="Total responses", value=str(count), inline=True)
            embed.add_field(
                name="Activated by",
                value=f"<@{active.activated_by_id}>",
                inline=True,
            )
            embed.add_field(
                name="Activated at",
                value=_fmt_dt(active.activated_at),
                inline=True,
            )
            if template:
                embed.add_field(
                    name="Fields",
                    value=str(len(template.fields)),
                    inline=True,
                )
        await interaction.followup.send(embed=embed, ephemeral=True)

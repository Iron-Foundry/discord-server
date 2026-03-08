from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from command_infra.checks import handle_check_failure, is_senior_staff, is_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry
from roles.models import SelectableRoleConfig

if TYPE_CHECKING:
    from roles.service import RoleService


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the rolepanel command group."""
    registry.add_group(
        HelpGroup(
            name="rolepanel",
            description="Create and manage self-assign role panels",
            commands=[
                HelpEntry(
                    "/rolepanel list",
                    "List all active role panels",
                    "Staff",
                ),
                HelpEntry(
                    "/rolepanel refresh <panel_id>",
                    "Force-sync a panel message with current state",
                    "Staff",
                ),
                HelpEntry(
                    "/rolepanel create <channel> <title>",
                    "Post a new role panel to a channel",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/rolepanel edit <panel_id>",
                    "Edit a panel's title or description via a modal",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/rolepanel addrole <panel_id> <role>",
                    "Add a role to a panel",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/rolepanel removerole <panel_id> <role>",
                    "Remove a role from a panel",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/rolepanel setemoji <panel_id> <role> <emoji>",
                    "Set the emoji for a role on a panel",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/rolepanel setmax <panel_id> <max>",
                    "Set the maximum number of selectable roles",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/rolepanel delete <panel_id>",
                    "Delete a role panel",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/rolepanel refreshall",
                    "Push the new button layout to all live panel messages",
                    "Senior Staff",
                ),
            ],
        )
    )


class RolePanelGroup(
    app_commands.Group, name="rolepanel", description="Manage role panels"
):
    """Slash commands for creating and managing self-assign role panels."""

    def __init__(self, service: RoleService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # Autocomplete
    # ------------------------------------------------------------------

    async def _panel_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(
                name=f"{p.title} ({p.panel_id[:8]})",
                value=p.panel_id,
            )
            for p in self._service.get_all_panels()
            if current.lower() in p.title.lower() or current.lower() in p.panel_id
        ]

    # ------------------------------------------------------------------
    # /rolepanel create
    # ------------------------------------------------------------------

    @app_commands.command(
        name="create", description="Post a new role panel to a channel"
    )
    @app_commands.describe(
        channel="Channel to post the panel in",
        title="Embed title",
        description="Embed description",
    )
    @is_senior_staff()
    async def create(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str = "",
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        panel = await self._service.create_panel(channel, title, description)
        await interaction.followup.send(
            f"Panel **{panel.title}** posted to {channel.mention} (`{panel.panel_id[:8]}`).",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /rolepanel edit
    # ------------------------------------------------------------------

    @app_commands.command(
        name="edit", description="Edit a panel's title or description via a modal"
    )
    @app_commands.describe(panel_id="Panel to edit")
    @is_senior_staff()
    async def edit(
        self,
        interaction: discord.Interaction,
        panel_id: str,
    ) -> None:
        panel = self._service.get_panel(panel_id)
        if panel is None:
            await interaction.response.send_message("Panel not found.", ephemeral=True)
            return
        modal = PanelEditModal(self._service, panel_id, panel.title, panel.description)
        await interaction.response.send_modal(modal)

    @edit.autocomplete("panel_id")
    async def edit_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._panel_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # /rolepanel addrole
    # ------------------------------------------------------------------

    @app_commands.command(name="addrole", description="Add a role to a panel")
    @app_commands.describe(
        panel_id="Panel to update",
        role="Role to add",
        label="Display label (defaults to role name)",
        description="Short description shown in the select menu",
        emoji="Emoji to show next to the label",
    )
    @is_senior_staff()
    async def addrole(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        role: discord.Role,
        label: str | None = None,
        description: str = "",
        emoji: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        config = SelectableRoleConfig(
            role_id=role.id,
            label=label or role.name,
            description=description,
            emoji=emoji,
        )
        success = await self._service.add_role(panel_id, config)
        if success:
            await interaction.followup.send(
                f"Added {role.mention} to the panel.", ephemeral=True
            )
        else:
            panel = self._service.get_panel(panel_id)
            if panel is None:
                await interaction.followup.send("Panel not found.", ephemeral=True)
            elif len(panel.roles) >= 25:
                await interaction.followup.send(
                    "Panel is full (25-role limit).", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"{role.mention} is already on this panel.", ephemeral=True
                )

    @addrole.autocomplete("panel_id")
    async def addrole_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._panel_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # /rolepanel removerole
    # ------------------------------------------------------------------

    @app_commands.command(name="removerole", description="Remove a role from a panel")
    @app_commands.describe(panel_id="Panel to update", role="Role to remove")
    @is_senior_staff()
    async def removerole(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        role: discord.Role,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.remove_role(panel_id, role.id)
        if success:
            await interaction.followup.send(
                f"Removed {role.mention} from the panel.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Panel not found or role was not on this panel.", ephemeral=True
            )

    @removerole.autocomplete("panel_id")
    async def removerole_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._panel_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # /rolepanel setemoji
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setemoji", description="Set the emoji for a role on a panel"
    )
    @app_commands.describe(
        panel_id="Panel to update", role="Role to update", emoji="New emoji"
    )
    @is_senior_staff()
    async def setemoji(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        role: discord.Role,
        emoji: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.set_emoji(panel_id, role.id, emoji)
        if success:
            await interaction.followup.send(
                f"Emoji for {role.mention} updated to {emoji}.", ephemeral=True
            )
        else:
            await interaction.followup.send("Panel or role not found.", ephemeral=True)

    @setemoji.autocomplete("panel_id")
    async def setemoji_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._panel_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # /rolepanel setmax
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setmax", description="Set the maximum number of selectable roles"
    )
    @app_commands.describe(
        panel_id="Panel to update",
        max="Maximum roles selectable at once (1–25); 0 = unlimited",
    )
    @is_senior_staff()
    async def setmax(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        max: int,
    ) -> None:
        if max < 0 or max > 25:
            await interaction.response.send_message(
                "Max must be between 0 and 25 (0 = unlimited).", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        value = max if max > 0 else None
        success = await self._service.set_max(panel_id, value)
        if success:
            label = str(max) if value is not None else "unlimited"
            await interaction.followup.send(
                f"Max selectable set to **{label}**.", ephemeral=True
            )
        else:
            await interaction.followup.send("Panel not found.", ephemeral=True)

    @setmax.autocomplete("panel_id")
    async def setmax_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._panel_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # /rolepanel delete
    # ------------------------------------------------------------------

    @app_commands.command(name="delete", description="Delete a role panel")
    @app_commands.describe(panel_id="Panel to delete")
    @is_senior_staff()
    async def delete(
        self,
        interaction: discord.Interaction,
        panel_id: str,
    ) -> None:
        panel = self._service.get_panel(panel_id)
        if panel is None:
            await interaction.response.send_message("Panel not found.", ephemeral=True)
            return

        # Confirmation via ephemeral with a confirm button
        view = _ConfirmDeleteView(self._service, panel_id, panel.title)
        await interaction.response.send_message(
            f"Are you sure you want to delete panel **{panel.title}**? This will also delete the message.",
            view=view,
            ephemeral=True,
        )

    @delete.autocomplete("panel_id")
    async def delete_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._panel_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # /rolepanel refresh
    # ------------------------------------------------------------------

    @app_commands.command(
        name="refresh", description="Force-sync a panel message with current state"
    )
    @app_commands.describe(panel_id="Panel to refresh")
    @is_staff()
    async def refresh(
        self,
        interaction: discord.Interaction,
        panel_id: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.refresh_panel(panel_id)
        if success:
            await interaction.followup.send("Panel refreshed.", ephemeral=True)
        else:
            await interaction.followup.send("Panel not found.", ephemeral=True)

    @refresh.autocomplete("panel_id")
    async def refresh_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._panel_autocomplete(interaction, current)

    # ------------------------------------------------------------------
    # /rolepanel refreshall
    # ------------------------------------------------------------------

    @app_commands.command(
        name="refreshall",
        description="Push the new button layout to all live panel messages",
    )
    @is_senior_staff()
    async def refreshall(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        count = await self._service.refresh_all_panels()
        await interaction.followup.send(f"Refreshed {count} panel(s).", ephemeral=True)

    # ------------------------------------------------------------------
    # /rolepanel list
    # ------------------------------------------------------------------

    @app_commands.command(name="list", description="List all active role panels")
    @is_staff()
    async def list_panels(self, interaction: discord.Interaction) -> None:
        panels = self._service.get_all_panels()
        embed = discord.Embed(title="Role Panels", color=discord.Color.blurple())

        if not panels:
            embed.description = "No role panels active."
        else:
            for p in panels:
                channel_mention = f"<#{p.channel_id}>"
                embed.add_field(
                    name=f"{p.title} (`{p.panel_id[:8]}`)",
                    value=(
                        f"Channel: {channel_mention}\n"
                        f"Roles: {len(p.roles)}\n"
                        f"Max selectable: {p.max_selectable or 'unlimited'}"
                    ),
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ------------------------------------------------------------------
# Modal for editing panel title / description
# ------------------------------------------------------------------


class PanelEditModal(discord.ui.Modal, title="Edit Role Panel"):
    """Modal for editing a role panel's title and description."""

    panel_title = discord.ui.TextInput(
        label="Title",
        placeholder="Panel title",
        max_length=100,
    )
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Describe this panel...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000,
    )

    def __init__(
        self,
        service: RoleService,
        panel_id: str,
        current_title: str,
        current_description: str,
    ) -> None:
        super().__init__()
        self._service = service
        self._panel_id = panel_id
        self.panel_title.default = current_title
        self.description.default = current_description or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.edit_panel(
            self._panel_id,
            title=self.panel_title.value,
            description=self.description.value,
        )
        if success:
            await interaction.followup.send("Panel updated.", ephemeral=True)
        else:
            await interaction.followup.send("Panel not found.", ephemeral=True)


# ------------------------------------------------------------------
# Confirmation view for delete
# ------------------------------------------------------------------


class _ConfirmDeleteView(discord.ui.View):
    """Ephemeral confirmation buttons for panel deletion."""

    def __init__(self, service: RoleService, panel_id: str, panel_title: str) -> None:
        super().__init__(timeout=60)
        self._service = service
        self._panel_id = panel_id
        self._panel_title = panel_title

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:  # noqa: ARG002
        await interaction.response.defer(ephemeral=True, thinking=True)
        success = await self._service.delete_panel(self._panel_id)
        if success:
            await interaction.followup.send(
                f"Panel **{self._panel_title}** deleted.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Panel not found or already deleted.", ephemeral=True
            )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:  # noqa: ARG002
        await interaction.response.send_message("Cancelled.", ephemeral=True)
        self.stop()

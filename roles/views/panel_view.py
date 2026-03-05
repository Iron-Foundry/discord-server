from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from roles.models import RolePanel
    from roles.service import RoleService


class RoleSelect(discord.ui.Select):
    """Select menu that lets members assign/remove panel roles."""

    def __init__(self, service: RoleService, panel: RolePanel) -> None:
        self._service = service
        self._panel_id = panel.panel_id

        if panel.roles:
            options = [
                discord.SelectOption(
                    label=r.label,
                    value=str(r.role_id),
                    description=r.description or None,
                    emoji=r.emoji,
                )
                for r in panel.roles
            ]
            max_values = min(
                panel.max_selectable
                if panel.max_selectable is not None
                else len(options),
                len(options),
            )
            max_values = max(max_values, 1)
        else:
            options = [
                discord.SelectOption(
                    label="No roles available",
                    value="__placeholder__",
                    default=True,
                )
            ]
            max_values = 1

        super().__init__(
            custom_id=f"role_panel_select:{panel.panel_id}",
            placeholder="Select roles…",
            min_values=0,
            max_values=max_values,
            options=options,
            disabled=not panel.roles,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        selected = [int(v) for v in self.values if v != "__placeholder__"]
        await self._service.handle_role_select(interaction, self._panel_id, selected)


class ClearAllButton(discord.ui.Button):
    """Button that removes all panel roles from the member."""

    def __init__(self, panel: RolePanel) -> None:
        self._panel_id = panel.panel_id
        super().__init__(
            custom_id=f"role_panel_clear:{panel.panel_id}",
            label="Clear All Roles",
            style=discord.ButtonStyle.danger,
            emoji="\U0001f5d1\ufe0f",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        # service is injected via the parent view
        view: RoleSelectView = self.view  # type: ignore[assignment]
        await view.service.handle_clear_all(interaction, self._panel_id)


class RoleSelectView(discord.ui.View):
    """Persistent view containing the role select menu and clear button."""

    def __init__(self, service: RoleService, panel: RolePanel) -> None:
        super().__init__(timeout=None)
        self.service = service
        self.add_item(RoleSelect(service, panel))
        self.add_item(ClearAllButton(panel))

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from roles.models import RolePanel
    from roles.service import RoleService


class ManageRolesButton(discord.ui.Button):
    """Persistent button that opens an ephemeral pre-populated role select."""

    def __init__(self, panel: RolePanel) -> None:
        self._panel_id = panel.panel_id
        super().__init__(
            custom_id=f"role_panel_manage:{panel.panel_id}",
            label="Manage My Roles",
            style=discord.ButtonStyle.primary,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        view: RoleSelectView = self.view  # type: ignore[assignment]
        await view.service.handle_manage_open(interaction, self._panel_id)


class ClearAllButton(discord.ui.Button):
    """Button that removes all panel roles from the member."""

    def __init__(self, panel: RolePanel) -> None:
        self._panel_id = panel.panel_id
        super().__init__(
            custom_id=f"role_panel_clear:{panel.panel_id}",
            label="Clear All Roles",
            style=discord.ButtonStyle.danger,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        view: RoleSelectView = self.view  # type: ignore[assignment]
        await view.service.handle_clear_all(interaction, self._panel_id)


class RoleSelectView(discord.ui.View):
    """Persistent view containing the manage roles button and clear button."""

    def __init__(self, service: RoleService, panel: RolePanel) -> None:
        super().__init__(timeout=None)
        self.service = service
        self.add_item(ManageRolesButton(panel))
        self.add_item(ClearAllButton(panel))


class EphemeralRoleSelect(discord.ui.Select):
    """Non-persistent select menu pre-populated with the member's current roles."""

    def __init__(
        self,
        service: RoleService,
        panel: RolePanel,
        member_current_role_ids: set[int],
    ) -> None:
        self._service = service
        self._panel_id = panel.panel_id

        if panel.roles:
            options = [
                discord.SelectOption(
                    label=r.label,
                    value=str(r.role_id),
                    description=r.description or None,
                    emoji=r.emoji,
                    default=r.role_id in member_current_role_ids,
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
            placeholder="Select roles…",
            min_values=0,
            max_values=max_values,
            options=options,
            disabled=not panel.roles,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        selected = [int(v) for v in self.values if v != "__placeholder__"]
        await self._service.handle_role_select(interaction, self._panel_id, selected)


class EphemeralRoleSelectView(discord.ui.View):
    """Short-lived view sent ephemerally with a pre-populated role select."""

    def __init__(
        self,
        service: RoleService,
        panel: RolePanel,
        member_current_role_ids: set[int],
    ) -> None:
        super().__init__(timeout=180)
        self.add_item(EphemeralRoleSelect(service, panel, member_current_role_ids))

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import discord
from loguru import logger

from core.service_base import Service
from roles.models import RolePanel, SelectableRoleConfig
from roles.repository import MongoRolePanelRepository
from roles.views.panel_view import EphemeralRoleSelectView, RoleSelectView


class RoleService(Service):
    """Manages role panels — creation, updates, persistence, and interaction handling."""

    def __init__(
        self,
        guild: discord.Guild,
        client: discord.Client,
        repo: MongoRolePanelRepository,
    ) -> None:
        self._guild = guild
        self._client = client
        self._repo = repo
        self._panels: dict[str, RolePanel] = {}

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Load all panels from MongoDB and re-attach persistent views."""
        await self._repo.ensure_indexes()
        panels = await self._repo.get_all_panels(self._guild.id)
        for panel in panels:
            self._panels[panel.panel_id] = panel
            view = RoleSelectView(self, panel)
            self._client.add_view(view, message_id=panel.message_id)
        logger.info(f"Reattached {len(panels)} role panel(s)")

    # ------------------------------------------------------------------
    # Panel lifecycle
    # ------------------------------------------------------------------

    async def create_panel(
        self,
        channel: discord.TextChannel,
        title: str,
        description: str = "",
    ) -> RolePanel:
        """Post a new role panel to *channel* and persist it."""
        panel_id = str(uuid4())
        panel = RolePanel(
            panel_id=panel_id,
            guild_id=self._guild.id,
            channel_id=channel.id,
            message_id=0,
            title=title,
            description=description,
        )
        embed = _build_embed(panel)
        view = RoleSelectView(self, panel)
        msg = await channel.send(embed=embed, view=view)
        panel.message_id = msg.id
        await self._repo.save_panel(panel)
        self._panels[panel_id] = panel
        self._client.add_view(view, message_id=msg.id)
        return panel

    async def add_role(self, panel_id: str, role_config: SelectableRoleConfig) -> bool:
        """Add a role to a panel. Returns False if the panel is full or role already exists."""
        panel = self._panels.get(panel_id)
        if not panel:
            return False
        if any(r.role_id == role_config.role_id for r in panel.roles):
            return False
        if len(panel.roles) >= 25:
            return False
        panel.roles.append(role_config)
        panel.updated_at = datetime.now(UTC)
        await self._repo.save_panel(panel)
        await self._refresh_panel(panel)
        return True

    async def remove_role(self, panel_id: str, role_id: int) -> bool:
        """Remove a role from a panel."""
        panel = self._panels.get(panel_id)
        if not panel:
            return False
        before = len(panel.roles)
        panel.roles = [r for r in panel.roles if r.role_id != role_id]
        if len(panel.roles) == before:
            return False
        panel.updated_at = datetime.now(UTC)
        await self._repo.save_panel(panel)
        await self._refresh_panel(panel)
        return True

    async def set_emoji(self, panel_id: str, role_id: int, emoji: str | None) -> bool:
        """Set the emoji for a role entry in a panel."""
        panel = self._panels.get(panel_id)
        if not panel:
            return False
        entry = next((r for r in panel.roles if r.role_id == role_id), None)
        if not entry:
            return False
        entry.emoji = emoji
        panel.updated_at = datetime.now(UTC)
        await self._repo.save_panel(panel)
        await self._refresh_panel(panel)
        return True

    async def edit_panel(
        self,
        panel_id: str,
        title: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Edit embed title and/or description."""
        panel = self._panels.get(panel_id)
        if not panel:
            return False
        if title is not None:
            panel.title = title
        if description is not None:
            panel.description = description
        panel.updated_at = datetime.now(UTC)
        await self._repo.save_panel(panel)
        await self._refresh_panel(panel)
        return True

    async def set_max(self, panel_id: str, max_selectable: int | None) -> bool:
        """Set the maximum number of selectable roles."""
        panel = self._panels.get(panel_id)
        if not panel:
            return False
        panel.max_selectable = max_selectable
        panel.updated_at = datetime.now(UTC)
        await self._repo.save_panel(panel)
        await self._refresh_panel(panel)
        return True

    async def delete_panel(self, panel_id: str) -> bool:
        """Delete a panel message and remove it from the database."""
        panel = self._panels.get(panel_id)
        if not panel:
            return False
        channel = self._guild.get_channel(panel.channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                msg = await channel.fetch_message(panel.message_id)
                await msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
        await self._repo.delete_panel(panel_id)
        del self._panels[panel_id]
        return True

    async def refresh_panel(self, panel_id: str) -> bool:
        """Force-sync a panel message with current state."""
        panel = self._panels.get(panel_id)
        if not panel:
            return False
        await self._refresh_panel(panel)
        return True

    def get_all_panels(self) -> list[RolePanel]:
        """Return all cached panels for this guild."""
        return list(self._panels.values())

    def get_panel(self, panel_id: str) -> RolePanel | None:
        """Return a single cached panel."""
        return self._panels.get(panel_id)

    # ------------------------------------------------------------------
    # Interaction handlers
    # ------------------------------------------------------------------

    async def handle_role_select(
        self,
        interaction: discord.Interaction,
        panel_id: str,
        selected_role_ids: list[int],
    ) -> None:
        """Apply the selected roles to the member, removing deselected panel roles."""
        panel = self._panels.get(panel_id)
        if not panel:
            await interaction.followup.send("Panel not found.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send(
                "This can only be used in a server.", ephemeral=True
            )
            return

        panel_role_ids = {r.role_id for r in panel.roles}
        current = {r.id for r in member.roles} & panel_role_ids
        desired = set(selected_role_ids) & panel_role_ids
        to_add = desired - current
        to_remove = current - desired

        if not to_add and not to_remove:
            await interaction.followup.send("No changes made.", ephemeral=True)
            return

        roles_to_add = [r for rid in to_add if (r := self._guild.get_role(rid))]
        roles_to_remove = [r for rid in to_remove if (r := self._guild.get_role(rid))]

        added: list[str] = []
        removed: list[str] = []

        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Role panel selection")
                added = [r.mention for r in roles_to_add]
            except discord.HTTPException as e:
                logger.error(
                    f"RolePanel: failed to add roles {[r.name for r in roles_to_add]} "
                    f"to {member}: {e}"
                )

        if roles_to_remove:
            try:
                await member.remove_roles(
                    *roles_to_remove, reason="Role panel deselection"
                )
                removed = [r.mention for r in roles_to_remove]
            except discord.HTTPException as e:
                logger.error(
                    f"RolePanel: failed to remove roles {[r.name for r in roles_to_remove]} "
                    f"from {member}: {e}"
                )

        parts: list[str] = []
        if added:
            parts.append(f"Added: {', '.join(added)}")
        if removed:
            parts.append(f"Removed: {', '.join(removed)}")

        if parts:
            await interaction.followup.send("  ".join(parts), ephemeral=True)
        else:
            await interaction.followup.send(
                "Could not apply role changes. Check that the bot role is above the panel roles in the server settings.",
                ephemeral=True,
            )

    async def handle_manage_open(
        self,
        interaction: discord.Interaction,
        panel_id: str,
    ) -> None:
        """Send an ephemeral role select pre-populated with the member's current roles."""
        panel = self._panels.get(panel_id)
        if not panel:
            await interaction.followup.send("Panel not found.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send(
                "This can only be used in a server.", ephemeral=True
            )
            return

        panel_role_ids = {r.role_id for r in panel.roles}
        member_current_role_ids = {r.id for r in member.roles} & panel_role_ids
        view = EphemeralRoleSelectView(self, panel, member_current_role_ids)
        await interaction.followup.send("Select your roles:", view=view, ephemeral=True)

    async def handle_clear_all(
        self,
        interaction: discord.Interaction,
        panel_id: str,
    ) -> None:
        """Remove all panel roles from the member."""
        panel = self._panels.get(panel_id)
        if not panel:
            await interaction.followup.send("Panel not found.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send(
                "This can only be used in a server.", ephemeral=True
            )
            return

        panel_role_ids = {r.role_id for r in panel.roles}
        roles_to_remove = [r for r in member.roles if r.id in panel_role_ids]

        if not roles_to_remove:
            await interaction.followup.send(
                "You have no panel roles to clear.", ephemeral=True
            )
            return

        try:
            await member.remove_roles(*roles_to_remove, reason="Role panel clear all")
            removed = [r.mention for r in roles_to_remove]
            await interaction.followup.send(
                f"Cleared: {', '.join(removed)}", ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(
                f"RolePanel: failed to clear roles {[r.name for r in roles_to_remove]} "
                f"from {member}: {e}"
            )
            await interaction.followup.send("Could not remove roles.", ephemeral=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def refresh_all_panels(self) -> int:
        """Refresh all panels. Returns count of panels refreshed."""
        for panel in self._panels.values():
            await self._refresh_panel(panel)
        return len(self._panels)

    async def _refresh_panel(self, panel: RolePanel) -> None:
        """Edit the panel message to reflect current state."""
        channel = self._guild.get_channel(panel.channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                f"Role panel channel {panel.channel_id} not found for panel {panel.panel_id}"
            )
            return
        try:
            msg = await channel.fetch_message(panel.message_id)
        except (discord.NotFound, discord.HTTPException) as exc:
            logger.warning(f"Could not fetch panel message {panel.message_id}: {exc}")
            return
        embed = _build_embed(panel)
        view = RoleSelectView(self, panel)
        await msg.edit(embed=embed, view=view)
        self._client.add_view(view, message_id=panel.message_id)


def _build_embed(panel: RolePanel) -> discord.Embed:
    """Build the embed for a role panel."""
    embed = discord.Embed(
        title=panel.title,
        description=panel.description or None,
        color=discord.Color.blurple(),
    )
    if panel.roles:
        lines: list[str] = []
        for r in panel.roles:
            prefix = f"{r.emoji} " if r.emoji else ""
            suffix = f" — {r.description}" if r.description else ""
            lines.append(f"{prefix}<@&{r.role_id}>{suffix}")
        embed.add_field(name="Available Roles", value="\n".join(lines), inline=False)
    return embed

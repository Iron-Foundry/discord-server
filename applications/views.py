from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from applications.service import ApplicationService


class ApplicationResetView(discord.ui.View):
    """Persistent controls attached to the running summary message."""

    def __init__(self, service: "ApplicationService", ticket_id: int) -> None:
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


class ApplicationCompleteView(discord.ui.View):
    """Posted after all application questions are answered.

    Unlike the survey equivalent, submitting does NOT auto-close the ticket
    so that staff can review the application and respond.
    """

    def __init__(self, service: "ApplicationService", ticket_id: int) -> None:
        super().__init__(timeout=None)
        self._service = service
        self._ticket_id = ticket_id

    @discord.ui.button(
        label="Submit Application", style=discord.ButtonStyle.success, emoji="📨"
    )
    async def submit_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.defer()
        self.stop()
        await self._service.handle_submit(self._ticket_id, interaction)

"""Party service — manages the panel and coordinates party operations."""

from __future__ import annotations

import asyncio
import os

import discord
from loguru import logger

from core.service_base import Service
from features.parties.pg_repository import PgPartyRepository
from features.parties.views.panel import PartyPanelView, build_panel_embed

SITE_URL = (
    os.getenv("FRONTEND_URL", "https://ironfoundry.cc")
    .split(",")[0]
    .strip()
    .rstrip("/")
)
_REFRESH_INTERVAL = 30  # seconds


class PartyService(Service):
    """Manages the persistent party panel and party lifecycle."""

    def __init__(
        self,
        guild: discord.Guild,
        repo: PgPartyRepository,
        client: discord.Client,
    ) -> None:
        self._guild = guild
        self._repo = repo
        self._client = client
        self._panel_message: discord.Message | None = None
        self._panel_channel: discord.TextChannel | None = None
        self._current_page: int = 0
        self._refresh_task: asyncio.Task | None = None

    @property
    def repo(self) -> PgPartyRepository:
        """Expose repository to views."""
        return self._repo

    @property
    def site_url(self) -> str:
        return SITE_URL

    # ── Service lifecycle ─────────────────────────────────────────────────

    async def initialize(self) -> None:
        """No-op — panel recovery requires the live guild cache."""

    async def post_ready(self) -> None:
        """Recover the panel and start the periodic refresh task."""
        await self._recover_panel()
        self._refresh_task = asyncio.create_task(
            self._periodic_refresh(), name="party-panel-refresh"
        )

    async def _periodic_refresh(self) -> None:
        while True:
            await asyncio.sleep(_REFRESH_INTERVAL)
            try:
                await self.refresh_panel()
            except Exception as exc:
                logger.warning("PartyService: refresh error — {}", exc)

    # ── Panel management ──────────────────────────────────────────────────

    async def setup_panel(self, channel: discord.TextChannel) -> None:
        """Post a fresh panel in *channel* and persist the config."""
        parties = await self._repo.get_active_parties()
        embed, page, _ = build_panel_embed(parties, 0, self._guild)
        view = PartyPanelView(self, parties, page, SITE_URL)

        self._panel_channel = channel
        self._current_page = 0
        self._panel_message = await channel.send(embed=embed, view=view)
        await self._repo.save_panel_config(
            self._guild.id, channel.id, self._panel_message.id
        )
        logger.info(
            "PartyService: panel posted in #{} (msg {})",
            channel.name,
            self._panel_message.id,
        )

    async def refresh_panel(self) -> None:
        """Edit the panel message to reflect current party state."""
        if not self._panel_message:
            return
        parties = await self._repo.get_active_parties()
        embed, page, _ = build_panel_embed(
            parties, self._current_page, self._guild
        )
        self._current_page = page  # clamp if parties were deleted
        view = PartyPanelView(self, parties, page, SITE_URL)
        try:
            await self._panel_message.edit(embed=embed, view=view)
        except discord.NotFound:
            logger.warning("PartyService: panel message deleted, clearing config")
            self._panel_message = None
            self._panel_channel = None
            await self._repo.clear_panel_config(self._guild.id)

    async def navigate(
        self, interaction: discord.Interaction, delta: int
    ) -> None:
        """Move the panel page by *delta* and refresh."""
        self._current_page = max(0, self._current_page + delta)
        await self.refresh_panel()
        await interaction.response.defer()

    async def _recover_panel(self) -> None:
        """Re-attach the view to the stored panel message after restart."""
        config = await self._repo.get_panel_config(self._guild.id)
        if not config:
            return
        channel_id, message_id = config
        channel = self._guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        self._panel_channel = channel
        try:
            self._panel_message = await channel.fetch_message(message_id)
            parties = await self._repo.get_active_parties()
            view = PartyPanelView(self, parties, 0, SITE_URL)
            self._client.add_view(view, message_id=message_id)
            await self.refresh_panel()
            logger.info(
                "PartyService: panel recovered (msg {})", message_id
            )
        except discord.NotFound:
            logger.warning(
                "PartyService: panel message {} not found, clearing config",
                message_id,
            )
            await self._repo.clear_panel_config(self._guild.id)

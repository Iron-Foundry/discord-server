"""Party service - manages the panel and coordinates party operations."""

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
_ALLOWED_MENTIONS = discord.AllowedMentions(roles=True)


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
        """No-op - panel recovery requires the live guild cache."""

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
                logger.warning("PartyService: refresh error - {}", exc)

    # ── Panel management ──────────────────────────────────────────────────

    async def _fetch_state(self) -> tuple[list, list[dict]]:
        """Return (parties, ping_roles) for building the panel."""
        parties = await self._repo.get_active_parties()
        ping_roles = await self._repo.get_ping_roles()
        return parties, ping_roles

    async def setup_panel(self, channel: discord.TextChannel) -> None:
        """Post a fresh panel in *channel* and persist the config."""
        parties, ping_roles = await self._fetch_state()
        embed, _, _ = build_panel_embed(parties, ping_roles, 0, self._guild)
        view = PartyPanelView(self, parties, ping_roles, 0, SITE_URL)

        self._panel_channel = channel
        self._panel_message = await channel.send(
            embed=embed, view=view, allowed_mentions=_ALLOWED_MENTIONS
        )
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
        parties, ping_roles = await self._fetch_state()
        embed, _, _ = build_panel_embed(parties, ping_roles, 0, self._guild)
        view = PartyPanelView(self, parties, ping_roles, 0, SITE_URL)
        try:
            await self._panel_message.edit(
                embed=embed, view=view, allowed_mentions=_ALLOWED_MENTIONS
            )
        except discord.NotFound:
            logger.warning(
                "PartyService: panel message deleted - recreating in #{}",
                self._panel_channel.name if self._panel_channel else "?",
            )
            channel = self._panel_channel
            self._panel_message = None
            self._panel_channel = None
            await self._repo.clear_panel_config(self._guild.id)
            if isinstance(channel, discord.TextChannel):
                await self.setup_panel(channel)

    async def _recover_panel(self) -> None:
        """Recover the panel on restart, recreating it if the message is gone."""
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
            await self.refresh_panel()
            logger.info(
                "PartyService: panel recovered and refreshed (msg {})",
                message_id,
            )
        except discord.NotFound:
            logger.warning(
                "PartyService: panel message {} gone - recreating in #{}",
                message_id,
                channel.name,
            )
            await self._repo.clear_panel_config(self._guild.id)
            await self.setup_panel(channel)

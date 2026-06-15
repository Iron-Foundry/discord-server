"""Info Panel service - manages the persistent info panel in Discord."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import discord
import httpx
from loguru import logger

from core.service_base import Service
from features.info_panel.models import InfoPanelConfig, InfoPanelState, PanelMessageState
from features.info_panel.pg_repository import PgInfoPanelRepository
from features.info_panel.views.builder import build_views

if TYPE_CHECKING:
    pass


class InfoPanelService(Service):
    """Manages the persistent info panel with configurable sections."""

    def __init__(
        self,
        guild: discord.Guild,
        repo: PgInfoPanelRepository,
        client: discord.Client,
    ) -> None:
        self._guild = guild
        self._repo = repo
        self._client = client
        self._messages: list[discord.Message] = []
        self._panel_channel: discord.TextChannel | None = None
        self._refresh_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        pass

    async def post_ready(self) -> None:
        await self._recover_panel()
        config = await self._repo.get_panel_config()
        if config.refresh_interval_minutes > 0:
            self._refresh_task = asyncio.create_task(
                self._auto_refresh_loop(), name="info-panel-refresh"
            )

    # ── Panel management ──────────────────────────────────────────────────

    async def post_panel(self, channel: discord.TextChannel) -> None:
        """Post fresh panel messages in channel and persist state."""
        config = await self._repo.get_panel_config()
        live_data = await self._fetch_live_data(config)
        views = build_views(config, live_data, self._guild)

        if not views:
            raise ValueError("No enabled sections to post.")

        self._panel_channel = channel
        self._messages = []
        new_state = InfoPanelState(channel_id=channel.id, messages=[])

        for i, view in enumerate(views):
            msg = await channel.send(view=view)
            self._messages.append(msg)
            new_state.messages.append(PanelMessageState(index=i, message_id=msg.id))
            logger.info("InfoPanel: posted message {} in #{}", msg.id, channel.name)

        await self._repo.save_panel_state(new_state)

        if config.refresh_interval_minutes > 0 and self._refresh_task is None:
            self._refresh_task = asyncio.create_task(
                self._auto_refresh_loop(), name="info-panel-refresh"
            )

    async def refresh_panel(self) -> None:
        """Fetch fresh data and edit all existing panel messages."""
        if not self._messages:
            logger.debug("InfoPanel: refresh skipped - no messages")
            return
        config = await self._repo.get_panel_config()
        live_data = await self._fetch_live_data(config)
        views = build_views(config, live_data, self._guild)

        for i, msg in enumerate(self._messages):
            view = views[i] if i < len(views) else discord.ui.LayoutView(timeout=None)
            try:
                await msg.edit(view=view)
            except discord.NotFound:
                logger.warning("InfoPanel: message {} gone during refresh", msg.id)
                await self._repo.clear_panel_state()
                self._messages = []
                return
            except discord.HTTPException as exc:
                logger.warning("InfoPanel: edit failed for msg {}: {}", msg.id, exc)

    async def clear_panel(self) -> None:
        """Delete panel messages and clear stored state."""
        for msg in self._messages:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass
        self._messages = []
        self._panel_channel = None
        await self._repo.clear_panel_state()

        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

    # ── Auto-refresh ──────────────────────────────────────────────────────

    async def _auto_refresh_loop(self) -> None:
        while True:
            config = await self._repo.get_panel_config()
            interval = config.refresh_interval_minutes
            if interval <= 0:
                await asyncio.sleep(60)
                continue
            await asyncio.sleep(interval * 60)
            try:
                await self.refresh_panel()
                logger.debug("InfoPanel: auto-refresh complete")
            except Exception as exc:
                logger.warning("InfoPanel: auto-refresh error: {}", exc)

    # ── Recovery ─────────────────────────────────────────────────────────

    async def _recover_panel(self) -> None:
        state = await self._repo.get_panel_state()
        if not state.messages or state.channel_id is None:
            return
        channel = self._guild.get_channel(state.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        self._panel_channel = channel
        recovered: list[discord.Message] = []
        for entry in sorted(state.messages, key=lambda m: m.index):
            try:
                msg = await channel.fetch_message(entry.message_id)
                recovered.append(msg)
            except discord.NotFound:
                logger.warning(
                    "InfoPanel: message {} not found on recovery - clearing state",
                    entry.message_id,
                )
                await self._repo.clear_panel_state()
                self._messages = []
                return
        self._messages = recovered
        logger.info("InfoPanel: recovered {} message(s) in #{}", len(recovered), channel.name)
        await self.refresh_panel()

    # ── Data fetching ─────────────────────────────────────────────────────

    async def _fetch_live_data(self, config: InfoPanelConfig) -> dict:
        api_url = os.getenv("API_BACKEND_URL", "").rstrip("/")
        if not api_url:
            return {}

        all_sections = [s for msg in config.messages for s in msg.sections]
        types = {s.type for s in all_sections}
        requests: list[tuple[str, str]] = []

        if "server_stats" in types:
            requests += [
                ("wom_stats", "/clan/wom-stats"),
                ("clan_stats", "/clan/stats"),
                ("ranking_stats", "/ranking/stats"),
            ]
        if "name_changes" in types:
            requests.append(("name_changes", "/clan/name-changes"))
        if "competitions" in types:
            requests.append(("competitions", "/clan/competitions"))

        for section in all_sections:
            if section.type == "achievements":
                requests.append(
                    ("achievements", f"/clan/recent-achievements?limit={section.count}")  # type: ignore[union-attr]
                )
            elif section.type == "personal_bests":
                requests.append(
                    ("personal_bests", f"/clan/personal-bests?limit={section.count}")  # type: ignore[union-attr]
                )

        if not requests:
            return {}

        async def _get(client: httpx.AsyncClient, key: str, url: str) -> tuple[str, object]:
            try:
                r = await client.get(f"{api_url}{url}")
                r.raise_for_status()
                return key, r.json()
            except Exception as exc:
                logger.warning("InfoPanel: {} fetch failed: {}", key, exc)
                return key, None

        async with httpx.AsyncClient(timeout=15.0) as client:
            pairs = await asyncio.gather(*(_get(client, k, u) for k, u in requests))

        return {k: v for k, v in pairs if v is not None}

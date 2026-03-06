from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import discord
from discord.utils import MISSING
from loguru import logger

from core.service_base import Service
from docket.models import (
    DocketConfig,
    DocketPanelRecord,
    DonationEntry,
    EventEntry,
    PanelType,
    TOCEntry,
)
from docket.panels.base import DocketPanel
from docket.providers.protocol import ExternalApiProvider
from docket.repository import MongoDocketRepository

if TYPE_CHECKING:
    pass


class DocketService(Service):
    """Manages live docket panels — sends, edits, and refreshes community dashboard."""

    def __init__(
        self,
        guild: discord.Guild,
        client: discord.Client,
        repo: MongoDocketRepository,
        panels: dict[PanelType, DocketPanel],
        providers: list[ExternalApiProvider],
    ) -> None:
        self._guild = guild
        self._client = client
        self._repo = repo
        self._panels = panels
        self._providers = providers
        self._config: DocketConfig | None = None
        self._records: dict[PanelType, DocketPanelRecord] = {}
        self._channel: discord.TextChannel | None = None
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Called during setup_hook — ensures indexes and starts providers."""
        await self._repo.ensure_indexes()
        self._config = await self._repo.get_config(self._guild.id)
        for provider in self._providers:
            await provider.start()
        logger.info("DocketService: initialized")

    async def post_ready(self) -> None:
        """Called after on_ready — resolves the channel and re-attaches panels."""
        if not self._config:
            logger.info(
                "DocketService: not configured — run /docket setup to get started"
            )
            return

        channel = self._guild.get_channel(self._config.channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.error(
                f"DocketService: channel {self._config.channel_id} not found — "
                "check config or run /docket setup again"
            )
            self._channel = None
            return

        self._channel = channel
        await self._restore_panels()
        self._start_refresh_loop()

    async def _restore_panels(self) -> None:
        """Re-attach or re-post each panel from saved state."""
        assert self._config is not None
        assert self._channel is not None

        for panel_type in self._config.panel_order:
            if panel_type not in self._panels:
                continue
            record = await self._repo.get_panel_record(
                self._guild.id, panel_type
            ) or DocketPanelRecord(guild_id=self._guild.id, panel_type=panel_type)

            if record.message_id != 0:
                try:
                    msg = await self._channel.fetch_message(record.message_id)
                    panel = self._panels[panel_type]
                    view = panel.build_view(record, self)
                    if view:
                        self._client.add_view(view, message_id=msg.id)
                    self._records[panel_type] = record
                    logger.debug(
                        f"DocketService: re-attached panel {panel_type} "
                        f"(msg {record.message_id})"
                    )
                    continue
                except discord.NotFound:
                    logger.warning(
                        f"DocketService: panel {panel_type} message not found — "
                        "re-posting"
                    )
                    record.message_id = 0

            await self._post_panel(panel_type, record)

    def _start_refresh_loop(self) -> None:
        task = asyncio.create_task(self._refresh_loop())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    # ------------------------------------------------------------------
    # Panel rendering helpers
    # ------------------------------------------------------------------

    async def _post_panel(
        self, panel_type: PanelType, record: DocketPanelRecord
    ) -> None:
        """Send a new message for the panel and persist the message ID."""
        if not self._channel:
            return
        panel = self._panels.get(panel_type)
        if not panel:
            return
        embeds = await panel.build_embeds(record)
        view = panel.build_view(record, self)
        msg = await self._channel.send(
            embeds=embeds, view=view if view is not None else MISSING
        )
        record.message_id = msg.id
        if view:
            self._client.add_view(view, message_id=msg.id)
        await self._repo.save_panel_record(record)
        self._records[panel_type] = record
        logger.debug(f"DocketService: posted panel {panel_type} (msg {msg.id})")

    async def _render_panel(self, panel_type: PanelType) -> None:
        """Edit the existing panel message to reflect current state."""
        if not self._channel:
            return
        record = self._records.get(panel_type)
        if not record:
            return
        panel = self._panels.get(panel_type)
        if not panel:
            return

        embeds = await panel.build_embeds(record)
        view = panel.build_view(record, self)
        try:
            msg = await self._channel.fetch_message(record.message_id)
            await msg.edit(embeds=embeds, view=view if view is not None else MISSING)
            if view:
                self._client.add_view(view, message_id=record.message_id)
        except discord.NotFound:
            logger.warning(
                f"DocketService: panel {panel_type} message deleted — re-posting. "
                "Use /docket reset to restore original order."
            )
            record.message_id = 0
            await self._post_panel(panel_type, record)
            return
        except discord.HTTPException:
            logger.error(
                f"DocketService: HTTP error editing panel {panel_type} — "
                "will retry next cycle"
            )
            return

        record.updated_at = datetime.now(UTC)
        await self._repo.save_panel_record(record)

    # ------------------------------------------------------------------
    # Refresh loop
    # ------------------------------------------------------------------

    async def _refresh_loop(self) -> None:
        last_refresh: dict[PanelType, float] = {}
        while True:
            try:
                now = asyncio.get_event_loop().time()
                for panel_type, panel in self._panels.items():
                    if panel.refresh_interval_seconds == 0:
                        continue
                    elapsed = now - last_refresh.get(panel_type, 0.0)
                    if elapsed >= panel.refresh_interval_seconds:
                        record = self._records.get(panel_type)
                        if record:
                            await panel.refresh(record)
                            await self._render_panel(panel_type)
                        last_refresh[panel_type] = asyncio.get_event_loop().time()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("DocketService: refresh loop error")
                await asyncio.sleep(60)

    # ------------------------------------------------------------------
    # Setup / reset
    # ------------------------------------------------------------------

    async def setup(self, channel: discord.TextChannel) -> None:
        """Configure the docket channel and post all panels."""
        panel_order = list(self._panels.keys())
        self._config = DocketConfig(
            guild_id=self._guild.id,
            channel_id=channel.id,
            panel_order=panel_order,
        )
        await self._repo.save_config(self._config)
        self._channel = channel
        self._records.clear()
        for pt in self._bg_tasks:
            pt.cancel()
        self._bg_tasks.clear()
        await self._restore_panels()
        self._start_refresh_loop()
        logger.info(f"DocketService: configured in #{channel.name}")

    async def reset(self) -> None:
        """Delete all panel messages and re-post them in order."""
        if not self._channel or not self._config:
            return

        for panel_type in self._config.panel_order:
            record = self._records.get(panel_type)
            if record and record.message_id != 0:
                try:
                    msg = await self._channel.fetch_message(record.message_id)
                    await msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
            await self._repo.delete_panel_record(self._guild.id, panel_type)

        self._records.clear()
        for panel_type in self._config.panel_order:
            if panel_type not in self._panels:
                continue
            fresh = DocketPanelRecord(guild_id=self._guild.id, panel_type=panel_type)
            await self._post_panel(panel_type, fresh)

    # ------------------------------------------------------------------
    # Staff mutation methods — events
    # ------------------------------------------------------------------

    async def add_event(self, entry: EventEntry) -> None:
        """Add an event entry and re-render the events panel."""
        record = self._get_or_create_record(PanelType.EVENTS)
        record.event_entries.append(entry)
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.EVENTS)

    async def remove_event(self, entry_id: str) -> bool:
        """Remove an event entry by ID. Returns True if found and removed."""
        record = self._records.get(PanelType.EVENTS)
        if not record:
            return False
        before = len(record.event_entries)
        record.event_entries = [
            e for e in record.event_entries if e.entry_id != entry_id
        ]
        if len(record.event_entries) == before:
            return False
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.EVENTS)
        return True

    # ------------------------------------------------------------------
    # Staff mutation methods — TOC
    # ------------------------------------------------------------------

    async def add_toc_entry(self, entry: TOCEntry) -> None:
        """Add a TOC entry and re-render the TOC panel."""
        record = self._get_or_create_record(PanelType.TOC)
        record.toc_entries.append(entry)
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.TOC)

    async def remove_toc_entry(self, entry_id: str) -> bool:
        """Remove a TOC entry by ID. Returns True if found and removed."""
        record = self._records.get(PanelType.TOC)
        if not record:
            return False
        before = len(record.toc_entries)
        record.toc_entries = [e for e in record.toc_entries if e.entry_id != entry_id]
        if len(record.toc_entries) == before:
            return False
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.TOC)
        return True

    async def move_toc_entry(self, entry_id: str, new_position: int) -> bool:
        """Update the position of a TOC entry. Returns True if found."""
        record = self._records.get(PanelType.TOC)
        if not record:
            return False
        entry = next((e for e in record.toc_entries if e.entry_id == entry_id), None)
        if not entry:
            return False
        entry.position = new_position
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.TOC)
        return True

    # ------------------------------------------------------------------
    # Staff mutation methods — donations
    # ------------------------------------------------------------------

    async def add_donation(self, entry: DonationEntry) -> None:
        """Add a donation entry and re-render the donations panel."""
        record = self._get_or_create_record(PanelType.DONATIONS)
        record.donation_entries.append(entry)
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.DONATIONS)

    async def remove_donation(self, entry_id: str) -> bool:
        """Remove a donation entry by ID. Returns True if found and removed."""
        record = self._records.get(PanelType.DONATIONS)
        if not record:
            return False
        before = len(record.donation_entries)
        record.donation_entries = [
            e for e in record.donation_entries if e.entry_id != entry_id
        ]
        if len(record.donation_entries) == before:
            return False
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.DONATIONS)
        return True

    # ------------------------------------------------------------------
    # Staff mutation methods — misc
    # ------------------------------------------------------------------

    async def force_refresh(self, panel_type: PanelType | None) -> bool:
        """Force-refresh one or all API panels. Returns False if not configured."""
        if not self._channel:
            return False
        targets = (
            [panel_type]
            if panel_type
            else [
                pt for pt, p in self._panels.items() if p.refresh_interval_seconds > 0
            ]
        )
        for pt in targets:
            panel = self._panels.get(pt)
            record = self._records.get(pt)
            if panel and record:
                await panel.refresh(record)
                await self._render_panel(pt)
        return True

    async def achievements_page(self, page: int) -> None:
        """Update the achievements panel page and re-render."""
        record = self._records.get(PanelType.ACHIEVEMENTS)
        if not record:
            return
        record.current_page = max(0, page)
        await self._repo.save_panel_record(record)
        await self._render_panel(PanelType.ACHIEVEMENTS)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def config(self) -> DocketConfig | None:
        """The current docket config, or None if not yet set up."""
        return self._config

    def get_record(self, panel_type: PanelType) -> DocketPanelRecord | None:
        """Return the in-memory record for a panel type."""
        return self._records.get(panel_type)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_or_create_record(self, panel_type: PanelType) -> DocketPanelRecord:
        """Return the cached record, creating a fresh one if missing."""
        if panel_type not in self._records:
            record = DocketPanelRecord(guild_id=self._guild.id, panel_type=panel_type)
            self._records[panel_type] = record
        return self._records[panel_type]

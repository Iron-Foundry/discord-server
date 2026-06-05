"""Party service - manages the panel and coordinates party operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os

import discord
from loguru import logger

from core.service_base import Service
from features.parties.pg_repository import PgPartyRepository
from features.parties.views.panel import build_panel_layout

SITE_URL = (
    os.getenv("FRONTEND_URL", "https://ironfoundry.cc")
    .split(",")[0]
    .strip()
    .rstrip("/")
)
_REFRESH_INTERVAL = 2.5  # seconds
_ALLOWED_MENTIONS = discord.AllowedMentions(roles=True)


def _state_hash(parties: list) -> str:
    """Stable hash of all display-relevant party state."""
    parts: list[str] = []
    for p in parties:
        member_ids = ",".join(sorted(m.user_id for m in p.members))
        scheduled = p.scheduled_at.isoformat() if p.scheduled_at else ""
        parts.append(
            f"{p.id}:{p.status}:{p.activity}:{p.description}:"
            f"{p.vibe}:{p.max_size}:{p.expires_at.isoformat()}:"
            f"{scheduled}:{member_ids}"
        )
    return hashlib.md5("|".join(parts).encode()).hexdigest()


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
        self._notify_task: asyncio.Task | None = None
        self._last_state_hash: str | None = None

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
        """Recover the panel and start background tasks."""
        await self._recover_panel()
        self._refresh_task = asyncio.create_task(
            self._periodic_refresh(), name="party-panel-refresh"
        )
        self._notify_task = asyncio.create_task(
            self._party_notify_subscriber(), name="party-notify-subscriber"
        )

    # ── DM notifications ──────────────────────────────────────────────────

    async def notify_members(
        self,
        party: object,
        message: str,
        *,
        exclude_user_id: str | None = None,
    ) -> None:
        """DM every party member, optionally skipping one user."""
        for member in party.members:  # type: ignore[attr-defined]
            if exclude_user_id and member.user_id == exclude_user_id:
                continue
            await self._dm_safe(member.user_id, content=message)

    async def _dm_safe(
        self,
        user_id: str,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
    ) -> None:
        try:
            user = await self._client.fetch_user(int(user_id))
            await user.send(content=content, embed=embed)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("PartyService: could not DM user {} - {}", user_id, exc)

    def _build_embed(self, data: dict) -> discord.Embed:
        embed = discord.Embed(
            title=data.get("title"),
            description=data.get("description"),
            color=data.get("color", 0x57F287),
            url=data.get("url"),
        )
        for field in data.get("fields", []):
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", True),
            )
        return embed

    async def _party_notify_subscriber(self) -> None:
        from valkey.asyncio import Valkey as ValkeyClient

        valkey_uri = os.getenv("VALKEY_URI", "redis://localhost:6379")
        while True:
            client: ValkeyClient = ValkeyClient.from_url(
                valkey_uri, socket_timeout=None
            )
            try:
                async with client.pubsub() as ps:
                    await ps.subscribe("foundry:party_notify")
                    logger.info("PartyService: subscribed to foundry:party_notify")
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            data = json.loads(raw["data"])
                            user_ids: list[str] = data.get("user_ids", [])
                            if "embed" in data:
                                embed = self._build_embed(data["embed"])
                                for uid in user_ids:
                                    await self._dm_safe(uid, embed=embed)
                            else:
                                message: str = data.get("message", "")
                                for uid in user_ids:
                                    await self._dm_safe(uid, content=message)
                        except Exception as exc:
                            logger.warning(
                                "PartyService: notify subscriber error - {}",
                                exc,
                            )
            except asyncio.CancelledError:
                logger.info("PartyService: notify subscriber shutting down")
                await client.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "PartyService: notify subscriber lost connection ({}), reconnecting in 5s",
                    exc,
                )
                await client.aclose()
                await asyncio.sleep(5)

    async def _periodic_refresh(self) -> None:
        while True:
            await asyncio.sleep(_REFRESH_INTERVAL)
            try:
                await self.refresh_panel()
            except Exception as exc:
                logger.warning("PartyService: refresh error - {}", exc)

    # ── Panel management ──────────────────────────────────────────────────

    async def _fetch_state(self) -> list:
        """Return active parties for building the panel."""
        return await self._repo.get_active_parties()

    async def setup_panel(self, channel: discord.TextChannel) -> None:
        """Post a fresh panel in *channel* and persist the config."""
        parties = await self._fetch_state()
        layout = build_panel_layout(parties, SITE_URL, self)

        self._panel_channel = channel
        self._panel_message = await channel.send(
            view=layout,
            allowed_mentions=_ALLOWED_MENTIONS,
        )
        self._last_state_hash = _state_hash(parties)
        await self._repo.save_panel_config(
            self._guild.id, channel.id, self._panel_message.id
        )
        logger.info(
            "PartyService: panel posted in #{} (msg {})",
            channel.name,
            self._panel_message.id,
        )

    async def refresh_panel(self) -> None:
        """Edit the panel message only when party state has changed."""
        if not self._panel_message:
            if isinstance(self._panel_channel, discord.TextChannel):
                await self.setup_panel(self._panel_channel)
            return
        parties = await self._fetch_state()
        new_hash = _state_hash(parties)
        if new_hash == self._last_state_hash:
            return
        layout = build_panel_layout(parties, SITE_URL, self)
        try:
            await self._panel_message.edit(
                view=layout,
                allowed_mentions=_ALLOWED_MENTIONS,
            )
            self._last_state_hash = new_hash
        except discord.NotFound:
            logger.warning(
                "PartyService: panel message deleted - recreating in #{}",
                self._panel_channel.name if self._panel_channel else "?",
            )
            channel = self._panel_channel
            self._panel_message = None
            self._panel_channel = None
            self._last_state_hash = None
            await self._repo.clear_panel_config(self._guild.id)
            if isinstance(channel, discord.TextChannel):
                await self.setup_panel(channel)
        except discord.HTTPException as exc:
            if exc.status == 400:
                # Legacy embed message cannot be upgraded to V2 in place
                logger.info(
                    "PartyService: upgrading legacy panel to Components V2 in #{}",
                    self._panel_channel.name if self._panel_channel else "?",
                )
                try:
                    await self._panel_message.delete()
                except discord.NotFound:
                    pass
                self._panel_message = None
                self._last_state_hash = None
                await self._repo.clear_panel_config(self._guild.id)
                if isinstance(self._panel_channel, discord.TextChannel):
                    await self.setup_panel(self._panel_channel)
            else:
                raise

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

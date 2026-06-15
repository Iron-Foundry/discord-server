"""Discord-side competition schedule service - creates polls and announces results."""

from __future__ import annotations

import asyncio
import json
import os

import discord
from loguru import logger

from core.service_base import Service
from .poll_provider import DiscordNativePollProvider, PollOption, PollProvider
from .views import build_results_embed

_VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")

_CH_CREATE_POLL = "foundry:comp_schedule:create_poll"
_CH_POLL_POSTED = "foundry:comp_schedule:poll_posted"
_CH_POLL_RESULT = "foundry:comp_schedule:poll_result"
_CH_CLOSE_POLL = "foundry:comp_schedule:close_poll"
_CH_ANNOUNCE = "foundry:comp_schedule:announce_results"


class CompScheduleService(Service):
    """Handles Discord poll creation and results announcement for the competition schedule."""

    def __init__(
        self,
        guild: discord.Guild,
        client: discord.Client,
        poll_provider: PollProvider | None = None,
    ) -> None:
        self._guild = guild
        self._client = client
        self._poll_provider: PollProvider = poll_provider or DiscordNativePollProvider()
        self._poll_task: asyncio.Task | None = None
        self._close_task: asyncio.Task | None = None
        self._announce_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        pass

    async def post_ready(self) -> None:
        self._poll_task = asyncio.create_task(
            self._create_poll_subscriber(), name="comp-schedule-poll-sub"
        )
        self._close_task = asyncio.create_task(
            self._close_poll_subscriber(), name="comp-schedule-close-sub"
        )
        self._announce_task = asyncio.create_task(
            self._announce_subscriber(), name="comp-schedule-announce-sub"
        )

    # ── Subscribers ───────────────────────────────────────────────────────

    async def _create_poll_subscriber(self) -> None:
        from valkey.asyncio import Valkey as ValkeyClient

        while True:
            client: ValkeyClient = ValkeyClient.from_url(
                _VALKEY_URI, socket_timeout=None
            )
            try:
                async with client.pubsub() as ps:
                    await ps.subscribe(_CH_CREATE_POLL)
                    logger.info(
                        "CompScheduleService: subscribed to {}", _CH_CREATE_POLL
                    )
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            data = json.loads(raw["data"])
                            asyncio.create_task(
                                self._handle_create_poll(data),
                                name=f"comp-poll-{data.get('run_id')}",
                            )
                        except Exception as exc:
                            logger.warning(
                                "CompScheduleService: create_poll handler error: {}",
                                exc,
                            )
            except asyncio.CancelledError:
                logger.info("CompScheduleService: poll subscriber shutting down")
                await client.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "CompScheduleService: poll subscriber lost connection ({}), reconnecting in 5s",
                    exc,
                )
                await client.aclose()
                await asyncio.sleep(5)

    async def _close_poll_subscriber(self) -> None:
        from valkey.asyncio import Valkey as ValkeyClient

        while True:
            client: ValkeyClient = ValkeyClient.from_url(
                _VALKEY_URI, socket_timeout=None
            )
            try:
                async with client.pubsub() as ps:
                    await ps.subscribe(_CH_CLOSE_POLL)
                    logger.info(
                        "CompScheduleService: subscribed to {}", _CH_CLOSE_POLL
                    )
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            data = json.loads(raw["data"])
                            asyncio.create_task(
                                self._handle_close_poll(data),
                                name=f"comp-close-{data.get('run_id')}",
                            )
                        except Exception as exc:
                            logger.warning(
                                "CompScheduleService: close_poll handler error: {}",
                                exc,
                            )
            except asyncio.CancelledError:
                logger.info("CompScheduleService: close subscriber shutting down")
                await client.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "CompScheduleService: close subscriber lost connection ({}), reconnecting in 5s",
                    exc,
                )
                await client.aclose()
                await asyncio.sleep(5)

    async def _announce_subscriber(self) -> None:
        from valkey.asyncio import Valkey as ValkeyClient

        while True:
            client: ValkeyClient = ValkeyClient.from_url(
                _VALKEY_URI, socket_timeout=None
            )
            try:
                async with client.pubsub() as ps:
                    await ps.subscribe(_CH_ANNOUNCE)
                    logger.info("CompScheduleService: subscribed to {}", _CH_ANNOUNCE)
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            data = json.loads(raw["data"])
                            asyncio.create_task(
                                self._handle_announce(data),
                                name=f"comp-announce-{data.get('run_id')}",
                            )
                        except Exception as exc:
                            logger.warning(
                                "CompScheduleService: announce handler error: {}", exc
                            )
            except asyncio.CancelledError:
                logger.info("CompScheduleService: announce subscriber shutting down")
                await client.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "CompScheduleService: announce subscriber lost connection ({}), reconnecting in 5s",
                    exc,
                )
                await client.aclose()
                await asyncio.sleep(5)

    # ── Handlers ─────────────────────────────────────────────────────────

    async def _resolve_text_channel(
        self, channel_id: int | str
    ) -> discord.TextChannel | None:
        cid = int(channel_id)
        channel = self._guild.get_channel(cid) or self._client.get_channel(cid)
        if channel is None:
            try:
                channel = await self._client.fetch_channel(cid)
            except discord.NotFound:
                logger.warning(
                    "CompScheduleService: channel {} not found (guild={})",
                    channel_id,
                    self._guild.id,
                )
                return None
            except discord.Forbidden:
                logger.warning(
                    "CompScheduleService: no access to channel {}", channel_id
                )
                return None
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "CompScheduleService: channel {} is not a text channel (type={})",
                channel_id,
                type(channel).__name__,
            )
            return None
        return channel

    async def _handle_create_poll(self, data: dict) -> None:
        run_id = data.get("run_id")
        channel_id = data.get("channel_id")
        options: list[PollOption] = data.get("options", [])
        duration_hours: float = data.get("poll_duration_hours", 24.0)
        title: str = data.get("title", "What should we compete on?")

        if not channel_id or not options:
            logger.warning(
                "CompScheduleService: invalid create_poll payload for run {}", run_id
            )
            return

        channel = await self._resolve_text_channel(channel_id)
        if channel is None:
            return

        try:
            question = f"Vote for the next {title} metric!"
            msg_id = await self._poll_provider.post_poll(
                channel, question, options, duration_hours
            )

            from valkey.asyncio import Valkey as ValkeyClient

            v = ValkeyClient.from_url(_VALKEY_URI)
            await v.publish(
                _CH_POLL_POSTED,
                json.dumps(
                    {
                        "run_id": run_id,
                        "discord_poll_message_id": msg_id,
                        "discord_poll_channel_id": channel.id,
                    }
                ),
            )
            await v.aclose()

            logger.info(
                "CompScheduleService: posted poll {} for run {} in channel {}",
                msg_id,
                run_id,
                channel_id,
            )
        except Exception as exc:
            logger.error(
                "CompScheduleService: failed handling create_poll for run {}: {}",
                run_id,
                exc,
            )

    async def _handle_close_poll(self, data: dict) -> None:
        run_id = data.get("run_id")
        channel_id = data.get("channel_id")
        message_id = data.get("message_id")
        options: list[PollOption] = data.get("options", [])

        if not channel_id or not message_id:
            logger.warning(
                "CompScheduleService: invalid close_poll payload for run {}", run_id
            )
            return

        channel = await self._resolve_text_channel(channel_id)
        if channel is None:
            return

        try:
            result = await self._poll_provider.collect_result(
                channel, int(message_id), options
            )

            from valkey.asyncio import Valkey as ValkeyClient

            v = ValkeyClient.from_url(_VALKEY_URI)
            if result["winning_metric"] is None:
                await v.publish(
                    _CH_POLL_RESULT, json.dumps({"run_id": run_id, "skipped": True})
                )
                logger.info(
                    "CompScheduleService: run {} poll closed with no votes", run_id
                )
            else:
                await v.publish(
                    _CH_POLL_RESULT,
                    json.dumps(
                        {
                            "run_id": run_id,
                            "winning_metric": result["winning_metric"],
                        }
                    ),
                )
                logger.info(
                    "CompScheduleService: run {} poll closed, winner: {}",
                    run_id,
                    result["winning_metric"],
                )
            await v.aclose()
        except Exception as exc:
            logger.error(
                "CompScheduleService: failed closing poll for run {}: {}",
                run_id,
                exc,
            )

    async def _handle_announce(self, data: dict) -> None:
        results_channel_id = data.get("results_channel_id")
        if not results_channel_id:
            logger.warning("CompScheduleService: announce missing results_channel_id")
            return

        channel = await self._resolve_text_channel(results_channel_id)
        if channel is None:
            return

        try:
            embed = build_results_embed(data)
            await channel.send(embed=embed)
            logger.info(
                "CompScheduleService: announced results for run {} in channel {}",
                data.get("run_id"),
                results_channel_id,
            )
        except Exception as exc:
            logger.error(
                "CompScheduleService: failed to announce results for run {}: {}",
                data.get("run_id"),
                exc,
            )

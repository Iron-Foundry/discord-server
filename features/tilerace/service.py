"""Tile race service - provisions Discord from commands api-backend publishes."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Coroutine
from typing import Any

import discord
from loguru import logger

from core.config import get_staff_role_ids
from core.service_base import Service

from . import api_client, provisioning

_VALKEY_URI = os.getenv("VALKEY_URI", "redis://localhost:6379")
_CHANNEL = "foundry:tilerace_discord"
_RECONNECT_DELAY = 5


class TileRaceService(Service):
    """Applies setup, sync and teardown commands to the guild.

    Holds no tile race state: every command carries the full desired shape, and
    the resulting object ids are handed straight back to api-backend.
    """

    def __init__(self, guild: discord.Guild) -> None:
        self._guild = guild
        self._task: asyncio.Task[None] | None = None
        self._pending: set[asyncio.Task[None]] = set()

    async def initialize(self) -> None:
        pass

    async def post_ready(self) -> None:
        self._task = asyncio.create_task(
            self._subscriber(), name="tilerace-discord-sub"
        )

    def _spawn(self, coro: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _subscriber(self) -> None:
        from valkey.asyncio import Valkey as ValkeyClient

        while True:
            client: ValkeyClient = ValkeyClient.from_url(
                _VALKEY_URI, socket_timeout=None
            )
            try:
                async with client.pubsub() as ps:
                    await ps.subscribe(_CHANNEL)
                    logger.info("TileRaceService: subscribed to {}", _CHANNEL)
                    async for raw in ps.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            command = json.loads(raw["data"])
                        except Exception as exc:
                            logger.warning("TileRaceService: bad payload - {}", exc)
                            continue
                        self._spawn(
                            self._handle(command),
                            f"tilerace-{command.get('action')}-{command.get('event_id')}",
                        )
            except asyncio.CancelledError:
                logger.info("TileRaceService: subscriber shutting down")
                await client.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "TileRaceService: subscriber lost connection ({}), reconnecting in {}s",
                    exc,
                    _RECONNECT_DELAY,
                )
                await client.aclose()
                await asyncio.sleep(_RECONNECT_DELAY)

    async def _handle(self, command: dict[str, Any]) -> None:
        action = command.get("action")
        event_id = str(command.get("event_id") or "")
        if not event_id:
            logger.warning("TileRaceService: command without an event_id, ignoring")
            return
        if action not in ("setup", "sync", "teardown", "teardown_team"):
            logger.warning("TileRaceService: unknown action {}", action)
            return
        staff = await self._staff_role()
        result = provisioning.empty_result()
        try:
            if action == "teardown_team":
                await provisioning.teardown_team(self._guild, command)
                logger.info(
                    "TileRaceService: removed a deleted team from event {}", event_id
                )
                return
            if action == "teardown":
                result = await provisioning.teardown(self._guild, command)
            else:
                await provisioning.apply(self._guild, command, staff, result)
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.error(
                "TileRaceService: {} failed part-way for event {} - {}",
                action,
                event_id,
                exc,
            )
            await api_client.report_result(event_id, result)
            return
        if await api_client.report_result(event_id, result):
            logger.info(
                "TileRaceService: {} complete for event {} ({} teams)",
                action,
                event_id,
                len(result["teams"]),
            )

    async def _staff_role(self) -> discord.Role | None:
        role_ids = await get_staff_role_ids()
        staff_id = role_ids.get("staff_role_id")
        return self._guild.get_role(staff_id) if staff_id else None

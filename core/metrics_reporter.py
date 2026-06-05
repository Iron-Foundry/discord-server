"""Background task that periodically reports service metrics to api-backend."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger
from sqlalchemy import func, select

from core.db import get_session_factory
from core.db.models import Ticket, User, UserAccount

if TYPE_CHECKING:
    import discord

_REPORT_INTERVAL = 300  # 5 minutes
_SERVICE_NAME = "discord-server"


class MetricsReporter:
    """Collects and POSTs per-module metrics to api-backend every 5 minutes."""

    def __init__(self, client: discord.Client) -> None:
        self._client = client
        self._api_url = os.getenv("API_BACKEND_URL", "").rstrip("/")
        self._api_key = os.getenv("METRICS_API_KEY")
        self._start_time = time.monotonic()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self._api_url or not self._api_key:
            logger.warning(
                "MetricsReporter: API_BACKEND_URL or API_KEY not set - metrics reporting disabled"
            )
            return
        self._task = asyncio.create_task(self._poll_loop(), name="metrics-reporter")
        logger.info("MetricsReporter started (interval={}s)", _REPORT_INTERVAL)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MetricsReporter stopped")

    async def _poll_loop(self) -> None:
        await asyncio.sleep(30)  # let bot finish connecting and DB init
        while True:
            await self._report_all()
            await asyncio.sleep(_REPORT_INTERVAL)

    async def _report_all(self) -> None:
        modules = await self._collect_all()
        async with httpx.AsyncClient(timeout=10) as http:
            for module_name, payload in modules.items():
                await self._post_report(http, module_name, payload)

    async def _collect_all(self) -> dict[str, dict[str, Any]]:
        uptime = int(time.monotonic() - self._start_time)
        guild = getattr(self._client, "_guild", None)
        guild_member_count = guild.member_count if guild else None

        modules: dict[str, dict[str, Any]] = {
            "bot": {
                "uptime_seconds": uptime,
                "guild_member_count": guild_member_count,
            }
        }

        try:
            session_factory = get_session_factory()
        except RuntimeError:
            return modules

        async with session_factory() as session:
            modules["tickets"] = await self._collect_tickets(session)
            modules["members"] = await self._collect_members(session)

        return modules

    async def _collect_tickets(self, session: Any) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        open_count = (
            await session.execute(
                select(func.count()).select_from(Ticket).where(Ticket.status == "open")
            )
        ).scalar_one()

        closed_today = (
            await session.execute(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.status == "closed", Ticket.closed_at >= today_start)
            )
        ).scalar_one()

        avg_result = (
            await session.execute(
                select(
                    func.avg(
                        func.extract(
                            "epoch",
                            Ticket.closed_at - Ticket.created_at,
                        )
                    )
                )
                .select_from(Ticket)
                .where(
                    Ticket.status == "closed",
                    Ticket.closed_at.isnot(None),
                    Ticket.closed_at >= now - timedelta(days=30),
                )
            )
        ).scalar_one()

        return {
            "open_count": open_count,
            "closed_today": closed_today,
            "avg_resolution_seconds_30d": round(avg_result or 0),
        }

    async def _collect_members(self, session: Any) -> dict[str, Any]:
        total_users = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()

        users_with_rsn = (
            await session.execute(
                select(
                    func.count(func.distinct(UserAccount.discord_user_id))
                ).select_from(UserAccount)
            )
        ).scalar_one()

        return {
            "total_users": total_users,
            "users_with_rsn": users_with_rsn,
        }

    async def _post_report(
        self, http: httpx.AsyncClient, module_name: str, metrics: dict[str, Any]
    ) -> None:
        uptime = int(time.monotonic() - self._start_time)
        payload = {
            "service_name": _SERVICE_NAME,
            "module_name": module_name,
            "uptime_seconds": uptime,
            "is_healthy": True,
            "metrics": metrics,
        }
        try:
            response = await http.post(
                f"{self._api_url}/metrics/report",
                json=payload,
                headers={"verification-code": self._api_key},
            )
            if response.status_code >= 400:
                logger.warning(
                    "MetricsReporter: {}/{} returned HTTP {} - {}",
                    _SERVICE_NAME,
                    module_name,
                    response.status_code,
                    response.text,
                )
            else:
                logger.debug(
                    "MetricsReporter: reported {}/{}", _SERVICE_NAME, module_name
                )
        except Exception as exc:
            logger.warning(
                "MetricsReporter: failed to report {}/{} - {}",
                _SERVICE_NAME,
                module_name,
                exc,
            )

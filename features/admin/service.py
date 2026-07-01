from __future__ import annotations

import discord
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.service_base import Service


class AdminService(Service):
    def __init__(
        self,
        guild: discord.Guild,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._guild = guild
        self._session_factory = session_factory

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    async def initialize(self) -> None:
        logger.info("Admin service initialized")

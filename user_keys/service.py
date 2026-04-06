from __future__ import annotations

import secrets

import discord
from loguru import logger

from core.service_base import Service
from user_keys.models import UserKey
from user_keys.repository import MongoUserKeyRepository


class UserKeyService(Service):
    """Manages per-user API keys for the Foundry API."""

    def __init__(self, guild: discord.Guild, repo: MongoUserKeyRepository) -> None:
        self._guild = guild
        self._repo = repo

    async def initialize(self) -> None:
        """Create indexes on startup."""
        await self._repo.ensure_indexes()
        logger.info("UserKeyService initialised")

    async def get_key(self, member: discord.Member) -> UserKey | None:
        """Return the member's current active key, or None."""
        return await self._repo.get_by_user(member.id)

    async def generate_key(self, member: discord.Member) -> UserKey:
        """Generate a new key for the member, replacing any existing one."""
        user_key = UserKey(
            discord_user_id=member.id,
            discord_username=str(member),
            guild_id=self._guild.id,
            guild_name=self._guild.name,
            key=secrets.token_urlsafe(32),
        )
        await self._repo.save(user_key)
        logger.info(f"UserKeyService: generated new key for {member} ({member.id})")
        return user_key

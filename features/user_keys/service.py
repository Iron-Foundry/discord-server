from __future__ import annotations

import os

import discord
from loguru import logger
from xkcdpass import xkcd_password as xp

from core.service_base import Service
from features.user_keys.models import UserKey
from features.user_keys.repository import MongoUserKeyRepository

_WORDLIST_PATH = os.path.join(os.path.dirname(__file__), "wordlist.txt")
_WORDLIST = xp.generate_wordlist(wordfile=_WORDLIST_PATH, min_length=3)


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
            key=xp.generate_xkcdpassword(_WORDLIST, numwords=5, delimiter="-"),
        )
        await self._repo.save(user_key)
        logger.info(f"UserKeyService: generated new key for {member} ({member.id})")
        return user_key

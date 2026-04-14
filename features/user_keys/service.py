from __future__ import annotations

import os
from typing import TYPE_CHECKING

import discord
from loguru import logger
from xkcdpass import xkcd_password as xp

from core.service_base import Service
from features.user_keys.models import UserKey
from features.user_keys.pg_repository import PgUserKeyRepository

if TYPE_CHECKING:
    from core.discord_client import DiscordClient

_WORDLIST_PATH = os.path.join(os.path.dirname(__file__), "wordlist.txt")
_WORDLIST = xp.generate_wordlist(wordfile=_WORDLIST_PATH, min_length=3)


class UserKeyService(Service):
    """Manages per-user API keys for the Foundry API."""

    def __init__(self, guild: discord.Guild, repo: PgUserKeyRepository) -> None:
        self._guild = guild
        self._repo = repo

    async def initialize(self) -> None:
        """Create indexes on startup."""
        await self._repo.ensure_indexes()
        logger.info("UserKeyService initialised")

    async def get_key(self, member: discord.Member) -> UserKey | None:
        """Return the member's current active key, or None."""
        return await self._repo.get_by_user(member.id)

    async def get_user_profile(self, member: discord.Member) -> dict | None:
        """Return the unified user profile for a member, or None."""
        return await self._repo.get_user_profile(member.id)

    async def link_rsn(self, member: discord.Member, rsn: str) -> None:
        """Link an RSN to a member's user profile."""
        await self._repo.link_rsn(member.id, rsn)
        logger.info(f"UserKeyService: linked RSN {rsn!r} for {member} ({member.id})")

    async def set_stats_opt_out(self, member: discord.Member, opt_out: bool) -> None:
        """Set or clear the stats opt-out flag for a member."""
        await self._repo.set_stats_opt_out(member.id, opt_out)

    async def post_ready(self) -> None:
        """Sync all current guild members once the member cache is populated."""
        await self.sync_all_members()

    async def sync_all_members(self) -> None:
        """Upsert a bare profile for every current guild member."""
        members = self._guild.members
        logger.info("UserKeyService: syncing {} guild member(s) to DB", len(members))
        for member in members:
            if member.bot:
                continue
            await self._repo.upsert_member(member)
        logger.info("UserKeyService: guild member sync complete")

    async def register_member(self, member: discord.Member) -> None:
        """Create a bare user profile for a new guild member."""
        await self._repo.upsert_member(member)
        logger.info("UserKeyService: registered new member {} ({})", member, member.id)

    async def unregister_member(self, member: discord.Member) -> None:
        """Remove a member's user profile on guild leave."""
        await self._repo.delete_user(member.id)
        logger.info("UserKeyService: removed member {} ({})", member, member.id)

    def register_events(self, client: DiscordClient) -> None:
        """Register join/leave listeners on the Discord client."""

        async def on_member_join(member: discord.Member) -> None:
            if member.guild.id != self._guild.id or member.bot:
                return
            await self.register_member(member)

        async def on_member_remove(member: discord.Member) -> None:
            if member.guild.id != self._guild.id or member.bot:
                return
            await self.unregister_member(member)

        client.add_listener(on_member_join, "on_member_join")
        client.add_listener(on_member_remove, "on_member_remove")

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
        await self._repo.upsert_user_profile(user_key)
        logger.info(f"UserKeyService: generated new key for {member} ({member.id})")
        return user_key

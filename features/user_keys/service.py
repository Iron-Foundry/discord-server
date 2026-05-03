from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

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

    async def get_user_accounts(self, member: discord.Member) -> list[dict]:
        """Return all linked RSN accounts for a member."""
        return await self._repo.get_user_accounts(member.id)

    async def add_account(self, member: discord.Member, rsn: str) -> str | None:
        """Add an alt RSN. Returns an error message or None on success."""
        error = await self._repo.add_account(member.id, rsn)
        if not error:
            logger.info(
                "UserKeyService: added alt RSN {!r} for {} ({})", rsn, member, member.id
            )
        return error

    async def set_primary_account(
        self, member: discord.Member, rsn: str
    ) -> str | None:
        """Promote an RSN to primary. Returns error message or None on success."""
        error = await self._repo.set_primary_account(member.id, rsn)
        if not error:
            logger.info(
                "UserKeyService: set primary RSN {!r} for {} ({})",
                rsn,
                member,
                member.id,
            )
        return error

    async def remove_account(self, member: discord.Member, rsn: str) -> str | None:
        """Remove a linked RSN. Returns error message or None on success."""
        error = await self._repo.remove_account(member.id, rsn)
        if not error:
            logger.info(
                "UserKeyService: removed RSN {!r} for {} ({})", rsn, member, member.id
            )
        return error

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
        ok = 0
        failed = 0
        for member in members:
            if member.bot:
                continue
            try:
                await self._repo.upsert_member(member)
                ok += 1
            except Exception as exc:
                logger.error(
                    "UserKeyService: failed to upsert member {} ({}): {}",
                    member,
                    member.id,
                    exc,
                )
                failed += 1
        logger.info(
            "UserKeyService: guild member sync complete - ok={} failed={}", ok, failed
        )

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

        async def on_member_update(
            before: discord.Member, after: discord.Member
        ) -> None:
            if after.guild.id != self._guild.id or after.bot:
                return
            if before.roles != after.roles:
                await self.register_member(after)

        client.add_listener(on_member_join, "on_member_join")
        client.add_listener(on_member_remove, "on_member_remove")
        client.add_listener(on_member_update, "on_member_update")

    async def generate_key(self, member: discord.Member) -> UserKey:
        """Generate a new key for the member, replacing any existing one."""
        user_key = UserKey(
            discord_user_id=member.id,
            discord_username=str(member),
            guild_id=self._guild.id,
            guild_name=self._guild.name,
            key=cast(
                str, xp.generate_xkcdpassword(_WORDLIST, numwords=5, delimiter="-")
            ),
        )
        await self._repo.save(user_key)
        await self._repo.upsert_user_profile(user_key)
        logger.info(f"UserKeyService: generated new key for {member} ({member.id})")
        return user_key

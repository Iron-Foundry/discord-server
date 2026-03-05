from __future__ import annotations

from dataclasses import dataclass

import discord
from loguru import logger

from broadcast.models import BroadcastConfig
from broadcast.repository import MongoBroadcastRepository


@dataclass
class BroadcastResult:
    """Result of a broadcast operation."""

    sent: int
    failed: int
    skipped: int  # bots and members with DMs disabled


class BroadcastService:
    """Sends DMs to all members of a configured role."""

    def __init__(self, guild: discord.Guild, repo: MongoBroadcastRepository) -> None:
        self._guild = guild
        self._repo = repo
        self._config: BroadcastConfig | None = None

    async def initialize(self) -> None:
        """Load config from the database."""
        await self._repo.ensure_indexes()
        self._config = await self._repo.get_config(self._guild.id)
        logger.info("BroadcastService initialised")

    async def set_role(self, role_id: int) -> None:
        """Persist the broadcast role for this guild."""
        config = self._config or BroadcastConfig(guild_id=self._guild.id)
        config.role_id = role_id
        self._config = config
        await self._repo.save_config(config)

    @property
    def role(self) -> discord.Role | None:
        """The configured broadcast role, or None if not set."""
        if not self._config or not self._config.role_id:
            return None
        return self._guild.get_role(self._config.role_id)

    async def broadcast_message(self, message: discord.Message) -> BroadcastResult:
        """DM the message to every non-bot member that has the broadcast role."""
        role = self.role
        if role is None:
            return BroadcastResult(sent=0, failed=0, skipped=0)

        embed = self._build_dm_embed(message)
        view = _jump_view(message.jump_url)

        sent = failed = skipped = 0
        for member in role.members:
            if member.bot:
                skipped += 1
                continue
            try:
                await member.send(embed=embed, view=view)
                sent += 1
            except discord.Forbidden:
                skipped += 1  # DMs disabled or blocked
            except discord.HTTPException:
                failed += 1

        logger.info(
            f"Broadcast complete: sent={sent} skipped={skipped} failed={failed}"
        )
        return BroadcastResult(sent=sent, failed=failed, skipped=skipped)

    def _build_dm_embed(self, message: discord.Message) -> discord.Embed:
        channel_name = getattr(message.channel, "name", str(message.channel.id))
        embed = discord.Embed(
            description=message.content or "*No text content*",
            color=discord.Color.blurple(),
            timestamp=message.created_at,
        )
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.display_avatar.url,
        )
        embed.set_footer(text=f"#{channel_name} · {self._guild.name}")
        if message.attachments:
            embed.add_field(
                name="Attachments",
                value="\n".join(a.url for a in message.attachments[:5]),
                inline=False,
            )
        return embed


def _jump_view(jump_url: str) -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="View Original",
            url=jump_url,
            style=discord.ButtonStyle.link,
        )
    )
    return view

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar


def register(registrar: EventRegistrar) -> None:
    """Register moderation event handlers."""
    service = registrar.service

    async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
        if guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Member Banned",
            color=CATEGORY_COLORS[LogCategory.MODERATION],
            timestamp=datetime.now(UTC),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention} (`{user}`)", inline=True)
        embed.set_footer(text=f"User ID: {user.id}")
        logger.debug(f"ActionLog[moderation]: {user} was banned")
        await service.post(LogCategory.MODERATION, embed)

    async def on_member_unban(guild: discord.Guild, user: discord.User) -> None:
        if guild.id != service.guild.id:
            return

        embed = discord.Embed(
            title="Member Unbanned",
            color=discord.Color.green(),
            timestamp=datetime.now(UTC),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention} (`{user}`)", inline=True)
        embed.set_footer(text=f"User ID: {user.id}")
        logger.debug(f"ActionLog[moderation]: {user} was unbanned")
        await service.post(LogCategory.MODERATION, embed)

    async def on_member_update(before: discord.Member, after: discord.Member) -> None:
        """Detect timeout changes."""
        if before.guild.id != service.guild.id:
            return
        if before.timed_out_until == after.timed_out_until:
            return

        if after.timed_out_until is not None:
            until = discord.utils.format_dt(after.timed_out_until, style="F")
            embed = discord.Embed(
                title="Member Timed Out",
                color=CATEGORY_COLORS[LogCategory.MODERATION],
                timestamp=datetime.now(UTC),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="User", value=after.mention, inline=True)
            embed.add_field(name="Until", value=until, inline=True)
            embed.set_footer(text=f"User ID: {after.id}")
            logger.debug(f"ActionLog[moderation]: {after} timed out until {until}")
            await service.post(LogCategory.MODERATION, embed)
        else:
            embed = discord.Embed(
                title="Timeout Removed",
                color=discord.Color.green(),
                timestamp=datetime.now(UTC),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="User", value=after.mention, inline=True)
            embed.set_footer(text=f"User ID: {after.id}")
            logger.debug(f"ActionLog[moderation]: {after} timeout removed")
            await service.post(LogCategory.MODERATION, embed)

    async def on_automod_rule_create(rule: discord.AutoModRule) -> None:
        if rule.guild_id != service.guild.id:
            return

        embed = discord.Embed(
            title="AutoMod Rule Created",
            color=CATEGORY_COLORS[LogCategory.MODERATION],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=rule.name, inline=True)
        embed.add_field(
            name="Enabled", value="Yes" if rule.enabled else "No", inline=True
        )
        embed.add_field(
            name="Event",
            value=str(rule.event_type).replace("AutoModEventType.", ""),
            inline=True,
        )
        embed.set_footer(text=f"Rule ID: {rule.id}")
        logger.debug(f"ActionLog[moderation]: automod rule '{rule.name}' created")
        await service.post(LogCategory.MODERATION, embed)

    async def on_automod_rule_update(rule: discord.AutoModRule) -> None:
        if rule.guild_id != service.guild.id:
            return

        embed = discord.Embed(
            title="AutoMod Rule Updated",
            color=CATEGORY_COLORS[LogCategory.MODERATION],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=rule.name, inline=True)
        embed.add_field(
            name="Enabled", value="Yes" if rule.enabled else "No", inline=True
        )
        embed.set_footer(text=f"Rule ID: {rule.id}")
        logger.debug(f"ActionLog[moderation]: automod rule '{rule.name}' updated")
        await service.post(LogCategory.MODERATION, embed)

    async def on_automod_rule_delete(rule: discord.AutoModRule) -> None:
        if rule.guild_id != service.guild.id:
            return

        embed = discord.Embed(
            title="AutoMod Rule Deleted",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=rule.name, inline=True)
        embed.set_footer(text=f"Rule ID: {rule.id}")
        logger.debug(f"ActionLog[moderation]: automod rule '{rule.name}' deleted")
        await service.post(LogCategory.MODERATION, embed)

    async def on_automod_action(
        execution: discord.AutoModActionExecution,
    ) -> None:
        if execution.guild_id != service.guild.id:
            return

        action_type = str(execution.action.type).replace("AutoModRuleActionType.", "")
        embed = discord.Embed(
            title="AutoMod Action Taken",
            color=CATEGORY_COLORS[LogCategory.MODERATION],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="User", value=f"<@{execution.user_id}>", inline=True)
        embed.add_field(name="Action", value=action_type, inline=True)
        if execution.channel_id:
            embed.add_field(
                name="Channel", value=f"<#{execution.channel_id}>", inline=True
            )
        if execution.content:
            embed.add_field(
                name="Matched Content",
                value=execution.content[:512],
                inline=False,
            )
        if execution.matched_keyword:
            embed.add_field(
                name="Matched Keyword",
                value=f"`{execution.matched_keyword}`",
                inline=True,
            )
        embed.set_footer(text=f"Rule ID: {execution.rule_id}")
        logger.debug(
            f"ActionLog[moderation]: automod {action_type} on user {execution.user_id}"
        )
        await service.post(LogCategory.MODERATION, embed)

    registrar.add("on_member_ban", on_member_ban)
    registrar.add("on_member_unban", on_member_unban)
    registrar.add("on_member_update", on_member_update)
    registrar.add("on_automod_rule_create", on_automod_rule_create)
    registrar.add("on_automod_rule_update", on_automod_rule_update)
    registrar.add("on_automod_rule_delete", on_automod_rule_delete)
    registrar.add("on_automod_action", on_automod_action)

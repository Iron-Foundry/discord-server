from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from loguru import logger

from action_log.models import CATEGORY_COLORS, LogCategory

if TYPE_CHECKING:
    from action_log.registrar import EventRegistrar

_STATUS_LABELS: dict[discord.EventStatus, str] = {
    discord.EventStatus.scheduled: "Scheduled",
    discord.EventStatus.active: "Started",
    discord.EventStatus.completed: "Completed",
    discord.EventStatus.cancelled: "Cancelled",
}


def register(registrar: EventRegistrar) -> None:
    """Register scheduled event handlers."""
    service = registrar.service

    async def on_scheduled_event_create(
        event: discord.ScheduledEvent,
    ) -> None:
        if event.guild_id != service.guild.id:
            return

        embed = discord.Embed(
            title="Scheduled Event Created",
            color=CATEGORY_COLORS[LogCategory.SCHEDULED],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=event.name, inline=True)
        if event.start_time:
            embed.add_field(
                name="Starts",
                value=discord.utils.format_dt(event.start_time, style="F"),
                inline=True,
            )
        if event.description:
            embed.add_field(
                name="Description",
                value=event.description[:512],
                inline=False,
            )
        if event.creator:
            embed.add_field(name="Created By", value=event.creator.mention, inline=True)
        embed.set_footer(text=f"Event ID: {event.id}")
        logger.debug(f"ActionLog[scheduled]: event '{event.name}' created")
        await service.post(LogCategory.SCHEDULED, embed)

    async def on_scheduled_event_update(
        before: discord.ScheduledEvent, after: discord.ScheduledEvent
    ) -> None:
        if before.guild_id != service.guild.id:
            return

        # Status transitions are surfaced as their own embed
        if before.status != after.status:
            new_status = _STATUS_LABELS.get(after.status, str(after.status))
            embed = discord.Embed(
                title=f"Event {new_status}",
                color=CATEGORY_COLORS[LogCategory.SCHEDULED],
                timestamp=datetime.now(UTC),
            )
            embed.add_field(name="Event", value=after.name, inline=True)
            embed.add_field(name="Status", value=new_status, inline=True)
            embed.set_footer(text=f"Event ID: {after.id}")
            logger.debug(f"ActionLog[scheduled]: '{after.name}' status → {new_status}")
            await service.post(LogCategory.SCHEDULED, embed)
            return

        # Other detail changes
        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** {before.name} → {after.name}")
        if before.description != after.description:
            lines.append("**Description:** updated")
        if before.start_time != after.start_time and after.start_time:
            lines.append(
                f"**Start Time:** "
                f"{discord.utils.format_dt(after.start_time, style='F')}"
            )

        if not lines:
            return

        embed = discord.Embed(
            title="Event Updated",
            description="\n".join(lines),
            color=CATEGORY_COLORS[LogCategory.SCHEDULED],
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Event", value=after.name, inline=True)
        embed.set_footer(text=f"Event ID: {after.id}")
        logger.debug(f"ActionLog[scheduled]: '{after.name}' updated")
        await service.post(LogCategory.SCHEDULED, embed)

    async def on_scheduled_event_delete(
        event: discord.ScheduledEvent,
    ) -> None:
        if event.guild_id != service.guild.id:
            return

        embed = discord.Embed(
            title="Scheduled Event Deleted",
            color=discord.Color.dark_gray(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Name", value=event.name, inline=True)
        if event.start_time:
            embed.add_field(
                name="Was Scheduled For",
                value=discord.utils.format_dt(event.start_time, style="F"),
                inline=True,
            )
        embed.set_footer(text=f"Event ID: {event.id}")
        logger.debug(f"ActionLog[scheduled]: event '{event.name}' deleted")
        await service.post(LogCategory.SCHEDULED, embed)

    registrar.add("on_scheduled_event_create", on_scheduled_event_create)
    registrar.add("on_scheduled_event_update", on_scheduled_event_update)
    registrar.add("on_scheduled_event_delete", on_scheduled_event_delete)

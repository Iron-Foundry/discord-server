"""Open one submission: ask api-backend what is owed, then make the thread."""

from __future__ import annotations

from typing import Any

import discord
from loguru import logger

from core.config import get_staff_role_ids

from . import api
from .card import SubmissionCard
from .layout import status_layout

_THREAD_MINUTES = 4320


async def open_submission(interaction: discord.Interaction) -> None:
    """Handle a Submit press. The interaction is already deferred, ephemerally."""
    try:
        context = await api.get_context(interaction.user.id)
    except api.ApiUnavailableError as exc:
        await interaction.followup.send(view=status_layout(str(exc)), ephemeral=True)
        return

    if context.get("is_finished"):
        await interaction.followup.send(
            view=status_layout("This tile race is over."), ephemeral=True
        )
        return
    if context.get("tile") is None:
        await interaction.followup.send(
            view=status_layout(
                "Your team is not standing on a tile that needs proof. Roll first."
            ),
            ephemeral=True,
        )
        return
    if not int(context.get("outstanding") or 0):
        await interaction.followup.send(
            view=status_layout(
                "Your current tile is already fully covered by submissions."
            ),
            ephemeral=True,
        )
        return

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send(
            view=status_layout("Submissions can only be opened from the panel."),
            ephemeral=True,
        )
        return

    thread = await _open_thread(channel, interaction.user, context)
    if thread is None:
        await interaction.followup.send(
            view=status_layout("Could not open a thread. Please tell staff."),
            ephemeral=True,
        )
        return

    await thread.send(
        view=SubmissionCard(context, interaction.user.id, await _staff_mention(channel))
    )
    await interaction.followup.send(
        view=status_layout(f"Post your proof in {thread.mention}."), ephemeral=True
    )


async def _open_thread(
    channel: discord.TextChannel,
    user: discord.User | discord.Member,
    context: dict[str, Any],
) -> discord.Thread | None:
    team = context.get("team") or {}
    name = f"{team.get('slug', 'team')}-tile-{context.get('path_position')}"
    try:
        thread = await channel.create_thread(
            name=name[:100],
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=_THREAD_MINUTES,
            reason="Tile race submission",
        )
        await thread.add_user(user)
    except discord.HTTPException as exc:
        logger.warning("tilerace submissions: thread creation failed - {}", exc)
        return None
    logger.info(
        "tilerace submissions: opened {} for {} on tile {}",
        thread.name,
        user,
        context.get("path_position"),
    )
    return thread


async def _staff_mention(channel: discord.TextChannel) -> str:
    role_ids = await get_staff_role_ids()
    staff_id = role_ids.get("staff_role_id")
    role = channel.guild.get_role(staff_id) if staff_id else None
    return role.mention if role else "Staff have been notified."

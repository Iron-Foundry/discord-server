"""Build, refresh, and remove the Discord shape of a tile race event.

`apply` is idempotent: setup and sync run the same code, so a team added after
the first setup is created on the next sync rather than needing a teardown.
"""

from __future__ import annotations

from typing import Any

import discord

from . import guild_ops, naming


def _int_or_none(value: Any) -> int | None:
    return int(value) if value not in (None, "") else None


def empty_result() -> dict[str, Any]:
    return {
        "category_id": None,
        "captains_role_id": None,
        "captains_channel_id": None,
        "teams": [],
    }


async def apply(
    guild: discord.Guild,
    command: dict[str, Any],
    staff: discord.Role | None,
    sink: dict[str, Any],
) -> None:
    """Create or update every object this event needs, recording ids as it goes.

    Ids land in *sink* the moment each object exists, so a caller that catches a
    failure part-way still knows what was created. Without that, a run that dies
    on team nine leaves nine orphaned roles nothing can find again.
    """
    event_name = str(command.get("event_name") or "Tile Race")
    toggles = command.get("permissions") or {}
    category = await guild_ops.ensure_category(
        guild,
        _int_or_none(command.get("category_id")),
        naming.category_name(event_name),
        staff,
    )
    sink["category_id"] = category.id
    captains_role = await guild_ops.ensure_role(
        guild,
        _int_or_none(command.get("captains_role_id")),
        naming.captains_role_name(event_name),
    )
    sink["captains_role_id"] = captains_role.id
    captains_channel = await guild_ops.ensure_text_channel(
        guild,
        category,
        _int_or_none(command.get("captains_channel_id")),
        "captains",
        captains_role,
        staff,
        toggles,
    )
    sink["captains_channel_id"] = captains_channel.id
    await guild_ops.reconcile_members(
        guild,
        captains_role,
        {int(uid) for uid in command.get("captain_user_ids", [])},
    )

    for team in command.get("teams", []):
        sink["teams"].append(await _apply_team(guild, category, team, staff, toggles))


async def _apply_team(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    team: dict[str, Any],
    staff: discord.Role | None,
    toggles: dict[str, bool],
) -> dict[str, Any]:
    role_name, text_name, voice_name = guild_ops.team_names(team)
    role = await guild_ops.ensure_role(
        guild, _int_or_none(team.get("role_id")), role_name
    )
    text = await guild_ops.ensure_text_channel(
        guild,
        category,
        _int_or_none(team.get("text_channel_id")),
        text_name,
        role,
        staff,
        toggles,
    )
    voice = await guild_ops.ensure_voice_channel(
        guild,
        category,
        _int_or_none(team.get("voice_channel_id")),
        voice_name,
        role,
        staff,
        toggles,
    )
    await guild_ops.reconcile_members(
        guild, role, {int(uid) for uid in team.get("member_user_ids", [])}
    )
    return {
        "team_id": int(team["team_id"]),
        "role_id": role.id,
        "text_channel_id": text.id,
        "voice_channel_id": voice.id,
    }


async def teardown_team(guild: discord.Guild, command: dict[str, Any]) -> None:
    """Delete one deleted team's objects, leaving the rest of the event standing.

    Nothing is reported back: the team row is already gone on the other side, so
    there are no ids left to clear.
    """
    team = command.get("team") or {}
    await guild_ops.delete_channel(guild, _int_or_none(team.get("text_channel_id")))
    await guild_ops.delete_channel(guild, _int_or_none(team.get("voice_channel_id")))
    await guild_ops.delete_role(guild, _int_or_none(team.get("role_id")))


async def teardown(guild: discord.Guild, command: dict[str, Any]) -> dict[str, Any]:
    """Delete everything this event owns and report every id as cleared.

    Every delete swallows a missing object, so a teardown always completes and
    always reports a clean slate even if someone deleted a channel by hand.
    """
    for team in command.get("teams", []):
        await guild_ops.delete_channel(guild, _int_or_none(team.get("text_channel_id")))
        await guild_ops.delete_channel(
            guild, _int_or_none(team.get("voice_channel_id"))
        )
        await guild_ops.delete_role(guild, _int_or_none(team.get("role_id")))
    await guild_ops.delete_channel(
        guild, _int_or_none(command.get("captains_channel_id"))
    )
    await guild_ops.delete_role(guild, _int_or_none(command.get("captains_role_id")))
    await guild_ops.delete_channel(guild, _int_or_none(command.get("category_id")))
    return empty_result()

"""Permission overwrites for the tile race category and its channels."""

from __future__ import annotations

import discord

_Overwrites = dict[
    "discord.Role | discord.Member | discord.Object", discord.PermissionOverwrite
]

_HIDDEN = discord.PermissionOverwrite(view_channel=False)
_VISIBLE = discord.PermissionOverwrite(view_channel=True)


def _staff_grant() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True, send_messages=True, manage_messages=True
    )


def _member_grant() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True, send_messages=True, connect=True, speak=True
    )


def category(guild: discord.Guild, staff: discord.Role | None) -> _Overwrites:
    """Category is hidden by default; each channel opens itself to its own role."""
    result: _Overwrites = {
        guild.default_role: _HIDDEN,
        guild.me: _VISIBLE,
    }
    if staff is not None:
        result[staff] = _staff_grant()
    return result


def team_channel(
    guild: discord.Guild, team_role: discord.Role, staff: discord.Role | None
) -> _Overwrites:
    """Only the team's own role, staff, and the bot can see a team channel."""
    result: _Overwrites = {
        guild.default_role: _HIDDEN,
        guild.me: _VISIBLE,
        team_role: _member_grant(),
    }
    if staff is not None:
        result[staff] = _staff_grant()
    return result


def captains_channel(
    guild: discord.Guild, captains_role: discord.Role, staff: discord.Role | None
) -> _Overwrites:
    """The cross-team captains room: captains and staff only."""
    return team_channel(guild, captains_role, staff)

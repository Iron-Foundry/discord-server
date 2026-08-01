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


def member_grant(extra: dict[str, bool] | None = None) -> discord.PermissionOverwrite:
    """The base grant a team role gets, plus whatever the event's toggles add."""
    grant = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, connect=True, speak=True
    )
    flags: dict[str, bool] = extra or {}
    for name, value in flags.items():
        setattr(grant, name, value)
    return grant


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
    guild: discord.Guild,
    team_role: discord.Role,
    staff: discord.Role | None,
    extra: dict[str, bool] | None = None,
) -> _Overwrites:
    """Only the team's own role, staff, and the bot can see a team channel."""
    result: _Overwrites = {
        guild.default_role: _HIDDEN,
        guild.me: _VISIBLE,
        team_role: member_grant(extra),
    }
    if staff is not None:
        result[staff] = _staff_grant()
    return result


def shared_channel(
    guild: discord.Guild,
    team_roles: list[discord.Role],
    staff: discord.Role | None,
    extra: dict[str, bool] | None = None,
) -> _Overwrites:
    """One channel every racing team can see, such as submissions."""
    result: _Overwrites = {
        guild.default_role: _HIDDEN,
        guild.me: _VISIBLE,
    }
    for role in team_roles:
        result[role] = member_grant(extra)
    if staff is not None:
        result[staff] = _staff_grant()
    return result


def captains_channel(
    guild: discord.Guild,
    captains_role: discord.Role,
    staff: discord.Role | None,
    extra: dict[str, bool] | None = None,
) -> _Overwrites:
    """The cross-team captains room: captains and staff only."""
    return team_channel(guild, captains_role, staff, extra)

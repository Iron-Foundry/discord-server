"""Elevated per-team channel permissions, applied onto channels that exist.

api-backend sends the event's toggles with every command. Each toggle only ever
grants: an unset toggle leaves the flag inherited rather than denied, so turning
one off never takes away a permission the role holds server-wide.

`pin_messages` is Discord's own narrow permission (discord.py 2.7), kept apart
from `manage_messages` so a team can pin without also being able to delete each
other's messages.
"""

from __future__ import annotations

from collections.abc import Mapping

import discord

_TEXT_GRANTS: dict[str, tuple[str, ...]] = {
    "pin_messages": ("pin_messages",),
    "manage_messages": ("manage_messages",),
    "mention_everyone": ("mention_everyone",),
    "manage_threads": (
        "manage_threads",
        "create_public_threads",
        "send_messages_in_threads",
    ),
    "manage_channel": ("manage_channels",),
}
_VOICE_GRANTS: dict[str, tuple[str, ...]] = {
    "manage_channel": ("manage_channels",),
    "voice_moderation": ("mute_members", "deafen_members", "move_members"),
}


def _flags(
    grants: Mapping[str, tuple[str, ...]], toggles: Mapping[str, object]
) -> dict[str, bool]:
    enabled: dict[str, bool] = {}
    for toggle, permissions in grants.items():
        if toggles.get(toggle):
            enabled.update(dict.fromkeys(permissions, True))
    return enabled


def text_flags(toggles: Mapping[str, object] | None) -> dict[str, bool]:
    return _flags(_TEXT_GRANTS, toggles or {})


def voice_flags(toggles: Mapping[str, object] | None) -> dict[str, bool]:
    return _flags(_VOICE_GRANTS, toggles or {})


async def sync_role_overwrite(
    channel: discord.abc.GuildChannel,
    role: discord.Role,
    desired: discord.PermissionOverwrite,
    reason: str,
) -> bool:
    """Bring one role's overwrite in line, touching nothing else on the channel.

    `set_permissions` replaces only this target's overwrite, so an overwrite
    someone added by hand in Discord survives and the channel is never
    recreated. An unchanged channel costs no API call at all.
    """
    if channel.overwrites_for(role) == desired:
        return False
    await channel.set_permissions(role, overwrite=desired, reason=reason)
    return True

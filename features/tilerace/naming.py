"""Channel and role names derived from the team name the website holds.

The website is the only source of a team's name, so every name Discord shows is
computed here from that one string. Nothing is stored on this side to drift.
"""

from __future__ import annotations

import re

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_CHANNEL_LIMIT = 100
_ROLE_LIMIT = 100


def channel_name(team_name: str, fallback_slug: str) -> str:
    """Discord lowercases and hyphenates text channel names, so do it up front."""
    slug = _NON_SLUG.sub("-", team_name.lower()).strip("-")
    return (slug or fallback_slug or "team")[:_CHANNEL_LIMIT]


def voice_name(team_name: str) -> str:
    return (team_name or "Team")[:_CHANNEL_LIMIT]


def role_name(team_name: str) -> str:
    return (team_name or "Team")[:_ROLE_LIMIT]


def category_name(event_name: str) -> str:
    return (event_name or "Tile Race")[:_CHANNEL_LIMIT]


def captains_role_name(event_name: str) -> str:
    return f"{event_name} Captains"[:_ROLE_LIMIT]

"""Embed builders for competition schedule announcements."""

from __future__ import annotations

import os

import discord

SITE_URL = (
    os.getenv("FRONTEND_URL", "https://ironfoundry.cc")
    .split(",")[0]
    .strip()
    .rstrip("/")
)

_MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


def build_results_embed(data: dict) -> discord.Embed:
    """Build a results announcement embed from announce_results payload."""
    title = data.get("competition_title", "Competition")
    metric = data.get("metric", "")
    wom_id = data.get("wom_competition_id")
    top_results: list[dict] = data.get("top_results", [])

    embed = discord.Embed(
        title=f"{title} - Results",
        color=0xFFD700,
    )

    if wom_id:
        embed.url = f"https://wiseoldman.net/competitions/{wom_id}"

    if not top_results:
        embed.description = "No participants recorded gains in this competition."
    else:
        lines: list[str] = []
        for entry in top_results:
            rank = entry.get("rank", 0)
            rsn = entry.get("rsn", "?")
            gained = entry.get("gained", 0)
            medal = _MEDAL.get(rank, f"**#{rank}**")
            gained_fmt = _fmt_gained(gained, metric)
            lines.append(f"{medal} **{rsn}** - {gained_fmt}")
        embed.description = "\n".join(lines)

    if wom_id:
        comp_path = f"/competitions/{wom_id}"
        embed.add_field(
            name="Full leaderboard",
            value=f"[View on Iron Foundry]({SITE_URL}{comp_path})",
            inline=False,
        )

    embed.set_footer(text="Competition ended")
    return embed


def _fmt_gained(gained: int, metric: str) -> str:
    """Format a gained value depending on metric type."""
    _skill_metrics = {
        "overall",
        "attack",
        "defence",
        "strength",
        "hitpoints",
        "ranged",
        "prayer",
        "magic",
        "cooking",
        "woodcutting",
        "fletching",
        "fishing",
        "firemaking",
        "crafting",
        "smithing",
        "mining",
        "herblore",
        "agility",
        "thieving",
        "slayer",
        "farming",
        "runecrafting",
        "hunter",
        "construction",
    }
    if metric.lower() in _skill_metrics:
        if gained >= 1_000_000:
            return f"{gained / 1_000_000:.2f}M xp"
        if gained >= 1_000:
            return f"{gained / 1_000:.1f}K xp"
        return f"{gained:,} xp"
    return f"{gained:,} kc"

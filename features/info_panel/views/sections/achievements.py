from __future__ import annotations

from datetime import datetime, timezone

import discord

from features.info_panel.models import AchievementsSection

_TYPE_EMOJI = {
    "drop": "💰",
    "level": "⚔️",
    "xp_milestone": "📊",
}


def _ts(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.rstrip("Z"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return f" <t:{int(dt.timestamp())}:R>"
    except (ValueError, OSError):
        return ""


def _fmt_value(event_type: str, value: int | None) -> str:
    if value is None:
        return ""
    if event_type == "drop":
        return f" ({value:,} gp)"
    if event_type == "xp_milestone":
        return f" ({value:,} xp)"
    if event_type == "level":
        return f" (lv {value})"
    return ""


def build(section: AchievementsSection, live_data: dict, guild: discord.Guild) -> list[discord.ui.Item]:
    achievements: list[dict] = live_data.get("achievements") or []
    shown = achievements[: section.count]

    lines: list[str] = ["## Recent Achievements", ""]
    if not shown:
        lines.append("*No recent achievements.*")
    else:
        for ach in shown:
            emoji = _TYPE_EMOJI.get(ach.get("type", ""), "🏆")
            player = ach.get("player") or "?"
            label = ach.get("label") or ""
            detail = ach.get("detail")
            value = ach.get("value")
            event_type = ach.get("type", "")
            ts = _ts(ach.get("timestamp"))
            desc = label
            if detail:
                desc = f"{label} ({detail})"
            val_str = _fmt_value(event_type, value)
            lines.append(f"{emoji} `{player}` - {desc}{val_str}{ts}")

    return [discord.ui.TextDisplay(content="\n".join(lines))]

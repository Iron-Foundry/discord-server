from __future__ import annotations

from datetime import datetime, timezone

import discord

from features.info_panel.models import PersonalBestsSection


def _fmt_time(seconds: int) -> str:
    mins, secs = divmod(seconds, 60)
    if mins >= 60:
        hours, mins = divmod(mins, 60)
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


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


def build(section: PersonalBestsSection, live_data: dict, guild: discord.Guild) -> list[discord.ui.Item]:
    pbs: list[dict] = live_data.get("personal_bests") or []
    shown = pbs[: section.count]

    lines: list[str] = ["## Rank 1 Personal Bests", ""]
    if not shown:
        lines.append("*No rank 1 personal bests recorded.*")
    else:
        for pb in shown:
            player = pb.get("player") or "?"
            activity = pb.get("activity") or "?"
            variant = pb.get("variant") or ""
            time_sec = pb.get("time_seconds")
            ts = _ts(pb.get("timestamp"))
            time_str = f" ({_fmt_time(int(float(time_sec)))})" if time_sec is not None else ""
            full_activity = f"{activity} - {variant}" if variant else activity
            lines.append(f"🥇 `{player}` - {full_activity}{time_str}{ts}")

    return [discord.ui.TextDisplay(content="\n".join(lines))]

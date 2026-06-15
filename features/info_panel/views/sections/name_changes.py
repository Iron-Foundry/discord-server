from __future__ import annotations

from datetime import datetime, timezone

import discord

from features.info_panel.models import NameChangesSection


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


def build(section: NameChangesSection, live_data: dict, guild: discord.Guild) -> list[discord.ui.Item]:
    changes: list[dict] = live_data.get("name_changes") or []
    shown = changes[: section.count]

    lines: list[str] = ["## Recent Name Changes", ""]
    if not shown:
        lines.append("*No recent name changes.*")
    else:
        for nc in shown:
            old = nc.get("old_name", "?")
            new = nc.get("new_name", "?")
            ts = _ts(nc.get("resolved_at"))
            lines.append(f"`{old}` -> `{new}`{ts}")

    return [discord.ui.TextDisplay(content="\n".join(lines))]

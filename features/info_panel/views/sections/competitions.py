from __future__ import annotations

import os
from datetime import datetime, timezone

import discord

from features.info_panel.models import CompetitionsSection

_WEB_APP_URL = os.getenv("FRONTEND_URL", "https://ironfoundry.cc").rstrip("/")


def _time_left(ms: int) -> str:
    d = ms // 86_400_000
    h = (ms % 86_400_000) // 3_600_000
    m = (ms % 3_600_000) // 60_000
    if d > 0:
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def _fmt_metric(metric: str) -> str:
    return metric.replace("_", " ").title()


def build(
    section: CompetitionsSection,
    live_data: dict,
    guild: discord.Guild,
) -> list[discord.ui.Item]:
    competitions: list[dict] = live_data.get("competitions", [])
    active = [c for c in competitions if c.get("status") in ("ongoing", "upcoming")]
    if not active:
        return []

    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    lines = ["## Competitions"]
    buttons: list[discord.ui.Button] = []

    for comp in active[:5]:
        status = comp.get("status", "")
        title = comp.get("title", "Unknown")
        metric = _fmt_metric(comp.get("metric", ""))
        comp_id = comp.get("id")
        url = f"{_WEB_APP_URL}/competitions/{comp_id}" if comp_id is not None else ""

        if status == "ongoing":
            ends_ms = int(datetime.fromisoformat(comp["endsAt"].replace("Z", "+00:00")).timestamp() * 1000)
            remaining = max(0, ends_ms - now_ms)
            lines.append(f"🟢 `{title}` · {metric} · ends in {_time_left(remaining)}")
            label = f"🟢 {title}"
        else:
            starts_ms = int(datetime.fromisoformat(comp["startsAt"].replace("Z", "+00:00")).timestamp() * 1000)
            remaining = max(0, starts_ms - now_ms)
            lines.append(f"🔵 `{title}` · {metric} · starts in {_time_left(remaining)}")
            label = f"🔵 {title}"

        if url:
            buttons.append(
                discord.ui.Button(
                    label=label[:80],
                    url=url,
                    style=discord.ButtonStyle.link,
                )
            )

    items: list[discord.ui.Item] = [discord.ui.TextDisplay(content="\n".join(lines))]
    if buttons:
        items.append(discord.ui.ActionRow(*buttons[:5]))
    return items

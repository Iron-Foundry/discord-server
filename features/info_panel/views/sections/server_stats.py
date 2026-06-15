from __future__ import annotations

import discord

from features.info_panel.models import ServerStatsSection


def _fmt_num(n: int | float) -> str:
    return f"{int(n):,}"


def build(section: ServerStatsSection, live_data: dict, guild: discord.Guild) -> list[discord.ui.Item]:
    wom = live_data.get("wom_stats") or {}
    clan = live_data.get("clan_stats") or {}
    ranking = live_data.get("ranking_stats") or {}

    lines: list[str] = ["## Clan Statistics", ""]

    member_count = wom.get("member_count", 0)
    total_ranked = ranking.get("total", 0)
    total_xp = wom.get("total_xp", 0)
    total_ehb = wom.get("total_ehb", 0)
    cox_kc = wom.get("cox_kc", 0)
    tob_kc = wom.get("tob_kc", 0)
    toa_kc = wom.get("toa_kc", 0)
    total_gp = clan.get("total_gp", 0)
    clog_items = clan.get("collection_log_items", 0)

    lines += [
        f"Members: `{_fmt_num(member_count)}`  |  Ranked: `{_fmt_num(total_ranked)}`",
        f"Total XP: `{_fmt_num(total_xp)}`  |  Total EHB: `{_fmt_num(total_ehb)}`",
        f"CoX: `{_fmt_num(cox_kc)}`  |  ToB: `{_fmt_num(tob_kc)}`  |  ToA: `{_fmt_num(toa_kc)}`",
        f"GP Looted: `{_fmt_num(total_gp)}`  |  Clog Items: `{_fmt_num(clog_items)}`",
    ]

    return [discord.ui.TextDisplay(content="\n".join(lines))]

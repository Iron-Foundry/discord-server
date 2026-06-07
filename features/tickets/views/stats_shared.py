"""Shared helpers for ticket stats layout views."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import discord

_PERIOD_DAYS: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}

_PERIOD_OPTIONS = [
    discord.SelectOption(label="Last 7 days", value="7d"),
    discord.SelectOption(label="Last 30 days", value="30d"),
    discord.SelectOption(label="Last 90 days", value="90d"),
    discord.SelectOption(label="All time", value="all"),
]

_PERIOD_LABELS: dict[str, str] = {
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "90d": "Last 90 days",
    "all": "All time",
}


def parse_period(period: str) -> datetime | None:
    days = _PERIOD_DAYS.get(period)
    return datetime.now(UTC) - timedelta(days=days) if days else None


def fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}h {m}m" if h else f"{m}m"


def period_label(period: str) -> str:
    return _PERIOD_LABELS.get(period, period)

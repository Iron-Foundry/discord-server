"""Plotly chart builders for ticket handler statistics."""

from __future__ import annotations

import asyncio
import io

import discord
import plotly.graph_objects as go
from loguru import logger

from tickets.models.stats import HandlerStats, LeaderboardEntry, SystemStats

_BG = "#313338"
_GRID = "#383a40"
_TEXT = "#dbdee1"
_BAR = "#5865F2"

_PERIOD_LABELS: dict[str, str] = {
    "7d": "Last 7 Days",
    "30d": "Last 30 Days",
    "90d": "Last 90 Days",
    "all": "All Time",
}


def _apply_base_layout(fig: go.Figure) -> None:
    """Apply the shared dark Discord-themed layout to a figure."""
    fig.update_layout(  # type: ignore[call-arg]
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font={"color": _TEXT, "family": "Arial, sans-serif"},
        margin={"l": 80, "r": 30, "t": 50, "b": 60},
        xaxis={"gridcolor": _GRID, "zerolinecolor": _GRID},
        yaxis={"gridcolor": _GRID, "zerolinecolor": _GRID},
    )


async def _render(
    fig: go.Figure, filename: str, width: int, height: int
) -> discord.File:
    """Render a Plotly figure to PNG in a thread and wrap as a discord.File."""
    img_bytes: bytes = await asyncio.to_thread(
        fig.to_image, format="png", width=width, height=height
    )
    return discord.File(io.BytesIO(img_bytes), filename=filename)


async def build_stats_chart(
    stats: HandlerStats, display_name: str, period: str = "all"
) -> discord.File | None:
    """Horizontal bar chart of ticket type breakdown for a single handler.

    Returns None if chart rendering fails.
    """
    period_label = _PERIOD_LABELS.get(period, period)

    if stats.type_breakdown:
        types = list(stats.type_breakdown.keys())
        counts = [stats.type_breakdown[t] for t in types]
        labels = [t.replace("_", " ").title() for t in types]
    else:
        labels, counts = ["No data"], [0]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=_BAR,
            text=counts,
            textposition="outside",
            textfont={"color": _TEXT},
        )
    )
    _apply_base_layout(fig)
    fig.update_layout(  # type: ignore[call-arg]
        title={
            "text": f"Tickets by Type — {display_name} ({period_label})",
            "font": {"color": _TEXT},
        },
    )
    try:
        return await _render(fig, "stats.png", width=700, height=350)
    except Exception as e:
        logger.warning(f"Failed to render stats chart for {display_name!r}: {e}")
        return None


async def build_leaderboard_chart(
    entries: list[LeaderboardEntry],
    names: dict[int, str],
    metric: str = "closed",
    period: str = "all",
) -> discord.File | None:
    """Vertical bar chart for the leaderboard.

    Args:
        entries: Ranked leaderboard entries.
        names: Mapping of staff_id → display name.
        metric: ``"closed"``, ``"resolution"``, or ``"participated"``.
        period: Period key used in the chart title.

    Returns None if chart rendering fails or there are no entries.
    """
    if not entries:
        return None

    period_label = _PERIOD_LABELS.get(period, period)
    labels = [names.get(e.staff_id, str(e.staff_id)) for e in entries]

    if metric == "resolution":
        values: list[float | int] = [
            round(e.avg_resolution_seconds / 3600, 2)
            if e.avg_resolution_seconds is not None
            else 0.0
            for e in entries
        ]
        y_title = "Avg Resolution (hours)"
        chart_title = f"Ticket Leaderboard — Avg Resolution Time ({period_label})"
    elif metric == "participated":
        values = [e.tickets_participated for e in entries]
        y_title = "Tickets Participated In"
        chart_title = f"Ticket Leaderboard — Tickets Participated In ({period_label})"
    else:
        values = [e.tickets_closed for e in entries]
        y_title = "Tickets Closed"
        chart_title = f"Ticket Leaderboard — Tickets Closed ({period_label})"

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker_color=_BAR,
            text=values,
            textposition="outside",
            textfont={"color": _TEXT},
        )
    )
    _apply_base_layout(fig)
    fig.update_layout(  # type: ignore[call-arg]
        title={"text": chart_title, "font": {"color": _TEXT}},
        yaxis={"title": y_title, "gridcolor": _GRID, "zerolinecolor": _GRID},
    )
    try:
        return await _render(fig, "leaderboard.png", width=700, height=400)
    except Exception as e:
        logger.warning(f"Failed to render leaderboard chart: {e}")
        return None


async def build_system_chart(
    stats: SystemStats, period: str = "all"
) -> discord.File | None:
    """Horizontal bar chart of ticket type breakdown for the system overview.

    Returns None if chart rendering fails.
    """
    period_label = _PERIOD_LABELS.get(period, period)

    if stats.type_breakdown:
        types = list(stats.type_breakdown.keys())
        counts = [stats.type_breakdown[t] for t in types]
        labels = [t.replace("_", " ").title() for t in types]
    else:
        labels, counts = ["No data"], [0]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=_BAR,
            text=counts,
            textposition="outside",
            textfont={"color": _TEXT},
        )
    )
    _apply_base_layout(fig)
    fig.update_layout(  # type: ignore[call-arg]
        title={
            "text": f"Tickets by Type — System Overview ({period_label})",
            "font": {"color": _TEXT},
        },
    )
    try:
        return await _render(fig, "system.png", width=700, height=350)
    except Exception as e:
        logger.warning(f"Failed to render system chart: {e}")
        return None

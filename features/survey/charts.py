from __future__ import annotations

import asyncio
import io
from concurrent.futures import ThreadPoolExecutor

import discord

from features.survey.models import SurveyField, SurveyResponse

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chart")

_BG = "#2f3136"
_FG = "#dcddde"
_BAR_COLOUR = "#5865f2"


def _build_bar_chart_bytes(labels: list[str], values: list[int], title: str) -> bytes:
    import plotly.graph_objects as go  # lazy import to avoid startup cost

    total = sum(values)
    text_labels = [
        f"{v}  ({v / total * 100:.0f}%)" if total > 0 else "0" for v in values
    ]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            text=text_labels,
            textposition="outside",
            marker_color=_BAR_COLOUR,
            cliponaxis=False,
        )
    )
    height = max(220, 110 + len(labels) * 55)
    fig.update_layout(
        title=dict(text=title, font=dict(color="#ffffff", size=15)),
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(color=_FG, size=13),
        margin=dict(l=170, r=130, t=60, b=30),
        height=height,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(autorange="reversed", color=_FG),
        bargap=0.35,
    )

    buf = io.BytesIO()
    fig.write_image(buf, format="png", scale=2)
    buf.seek(0)
    return buf.read()


async def generate_field_chart(
    field: SurveyField, responses: list[SurveyResponse]
) -> discord.File | None:
    """Return a PNG chart for yes_no and select fields, or None for text fields."""
    loop = asyncio.get_event_loop()

    if field.type == "yes_no":
        answered = [r for r in responses if field.id in r.answers]
        if not answered:
            return None
        yes = sum(1 for r in answered if r.answers[field.id] is True)
        no = sum(1 for r in answered if r.answers[field.id] is False)
        png = await loop.run_in_executor(
            _EXECUTOR,
            _build_bar_chart_bytes,
            ["Yes", "No"],
            [yes, no],
            field.label,
        )
        return discord.File(io.BytesIO(png), filename=f"chart_{field.id}.png")

    if field.type == "select":
        answered = [r for r in responses if field.id in r.answers]
        if not answered:
            return None
        counts: dict[str, int] = {opt: 0 for opt in field.options}
        for r in answered:
            val = r.answers[field.id]
            items = val if isinstance(val, list) else [val]
            for item in items:
                if isinstance(item, str) and item in counts:
                    counts[item] += 1
        labels = list(counts.keys())
        values = list(counts.values())
        png = await loop.run_in_executor(
            _EXECUTOR,
            _build_bar_chart_bytes,
            labels,
            values,
            field.label,
        )
        return discord.File(io.BytesIO(png), filename=f"chart_{field.id}.png")

    return None


async def generate_summary_charts(
    template_fields: list[SurveyField],
    responses: list[SurveyResponse],
) -> list[tuple[SurveyField, discord.File]]:
    """Generate charts for all chartable fields; returns (field, file) pairs."""
    results: list[tuple[SurveyField, discord.File]] = []
    for field in template_fields:
        chart = await generate_field_chart(field, responses)
        if chart is not None:
            results.append((field, chart))
    return results

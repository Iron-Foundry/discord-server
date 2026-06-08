"""Pull Rank Score button and RSN modal for Join CC / Rank Up tickets."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import discord
import httpx
from loguru import logger
from sqlalchemy import select, update

from core.common.ticket_types import TicketTypeId
from core.db import get_session_factory
from core.db.models import Config, User, UserAccount

if TYPE_CHECKING:
    from features.tickets.ticket_service import TicketService

_RANK_TICKET_TYPES = {TicketTypeId.RANKUP.value, TicketTypeId.JOIN_CC.value}


async def _get_rank_pull_set_primary() -> bool:
    """Read the rank_pull_set_primary toggle from the DB config."""
    try:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Config.value).where(Config.guild_id == 0, Config.key == "ticket_features")
            )
            data = result.scalar_one_or_none() or {}
            return bool(data.get("rank_pull_set_primary", False))
    except Exception as exc:
        logger.warning("Could not read ticket_features config: {}", exc)
        return False


async def _set_primary_account(member: discord.Member, rsn: str) -> bool:
    """Set RSN as primary only if the user has no primary account yet.

    Creates User and/or UserAccount rows if they don't exist.
    Skips if the user already has a primary, or the RSN is held by another user.
    Returns True if the primary was set.
    """
    from datetime import datetime, UTC

    discord_user_id = member.id

    try:
        async with get_session_factory()() as session:
            existing_primary = await session.execute(
                select(UserAccount.id).where(
                    UserAccount.discord_user_id == discord_user_id,
                    UserAccount.is_primary == True,  # noqa: E712
                )
            )
            if existing_primary.scalar_one_or_none() is not None:
                return False

            other_owner = await session.execute(
                select(UserAccount.discord_user_id).where(
                    UserAccount.rsn.ilike(rsn),
                    UserAccount.discord_user_id != discord_user_id,
                )
            )
            if other_owner.scalar_one_or_none() is not None:
                logger.warning(
                    "Rank pull: RSN {} already linked to another user - skipping", rsn
                )
                return False

            now = datetime.now(UTC)

            user_exists = await session.execute(
                select(User.discord_user_id).where(
                    User.discord_user_id == discord_user_id
                )
            )
            if user_exists.scalar_one_or_none() is None:
                role_ids = [str(r.id) for r in member.roles if r.name != "@everyone"]
                session.add(User(
                    discord_user_id=discord_user_id,
                    discord_username=member.name,
                    discord_avatar_url=str(member.display_avatar.url),
                    guild_id=member.guild.id,
                    rsn=rsn,
                    discord_roles=role_ids,
                    created_at=now,
                    updated_at=now,
                ))

            existing_account = await session.execute(
                select(UserAccount).where(
                    UserAccount.discord_user_id == discord_user_id,
                    UserAccount.rsn.ilike(rsn),
                )
            )
            account = existing_account.scalar_one_or_none()
            if account is None:
                session.add(UserAccount(
                    discord_user_id=discord_user_id,
                    rsn=rsn,
                    is_primary=True,
                    created_at=now,
                ))
            else:
                account.is_primary = True
                await session.execute(
                    update(User)
                    .where(User.discord_user_id == discord_user_id)
                    .values(rsn=account.rsn)
                )

            await session.commit()
            return True
    except Exception as exc:
        logger.error("Failed to set primary account for {}: {}", discord_user_id, exc)
        return False


async def _build_rank_score_chart(
    rsn: str,
    rank: str,
    points: int,
    boss_points: int,
    skill_points: int,
) -> discord.File | None:
    """Horizontal stacked bar chart showing boss vs skill point breakdown."""
    try:
        import asyncio
        import io
        import plotly.graph_objects as go

        _BG = "#313338"
        _GRID = "#383a40"
        _TEXT = "#dbdee1"
        _BOSS_COLOR = "#5865F2"
        _SKILL_COLOR = "#57F287"

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Boss Points",
            x=[boss_points],
            y=[rsn],
            orientation="h",
            marker_color=_BOSS_COLOR,
            text=[f"{boss_points:,}"],
            textposition="inside",
            textfont={"color": _TEXT},
        ))
        fig.add_trace(go.Bar(
            name="Skill Points",
            x=[skill_points],
            y=[rsn],
            orientation="h",
            marker_color=_SKILL_COLOR,
            text=[f"{skill_points:,}"],
            textposition="inside",
            textfont={"color": "#1a1a2e"},
        ))

        fig.update_layout(
            barmode="stack",
            paper_bgcolor=_BG,
            plot_bgcolor=_BG,
            font={"color": _TEXT, "family": "Arial, sans-serif"},
            margin={"l": 80, "r": 120, "t": 60, "b": 40},
            xaxis={"gridcolor": _GRID, "zerolinecolor": _GRID, "tickfont": {"color": _TEXT}},
            yaxis={"gridcolor": _GRID, "zerolinecolor": _GRID, "tickfont": {"color": _TEXT}},
            legend={"orientation": "h", "x": 0, "y": -0.15, "font": {"color": _TEXT}},
            title={
                "text": f"{rsn} - {rank} ({points:,} pts total)",
                "font": {"color": _TEXT, "size": 16},
                "x": 0.5,
            },
            annotations=[{
                "x": 1.01,
                "y": 0.5,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "left",
                "text": f"<b>{points:,}</b><br>Total",
                "showarrow": False,
                "font": {"color": _TEXT, "size": 13},
            }],
        )

        img_bytes: bytes = await asyncio.to_thread(
            fig.to_image, format="png", width=700, height=220
        )
        return discord.File(io.BytesIO(img_bytes), filename="rank_score.png")
    except Exception as exc:
        logger.warning("Failed to render rank score chart: {}", exc)
        return None


class RsnModal(discord.ui.Modal, title="Pull Rank Score"):
    rsn_input = discord.ui.TextInput(
        label="RSN (RuneScape Name)",
        placeholder="Enter the player's RSN...",
        min_length=1,
        max_length=12,
    )

    def __init__(self, service: "TicketService", ticket_id: int) -> None:
        super().__init__()
        self._service = service
        self._ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        ticket = self._service.get_ticket_by_id(self._ticket_id)
        if not ticket:
            await interaction.followup.send("Ticket not found.", ephemeral=True)
            return

        rsn = self.rsn_input.value.strip()
        api_url = os.getenv("API_BACKEND_URL", "").rstrip("/")
        if not api_url:
            await interaction.followup.send(
                "API_BACKEND_URL not configured.", ephemeral=True
            )
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{api_url}/ranking/player/{rsn}")
        except Exception as exc:
            logger.error("Rank pull HTTP error for {!r}: {}", rsn, exc)
            await interaction.followup.send(
                "Failed to reach the ranking API. Try again later.", ephemeral=True
            )
            return

        if resp.status_code == 404:
            await interaction.followup.send(
                f"No ranking data found for **{rsn}**. Double-check the RSN and try again.",
                ephemeral=True,
            )
            return

        if resp.status_code != 200:
            await interaction.followup.send(
                f"Ranking API returned status {resp.status_code}. Try again later.",
                ephemeral=True,
            )
            return

        data = resp.json()
        rank: str = data.get("rank", "No Rank")
        points: int = data.get("points", 0)
        boss_points: int = data.get("boss_points", 0)
        skill_points: int = data.get("skill_points", 0)
        stats_opt_out: bool = data.get("stats_opt_out", False)

        chart_file = await _build_rank_score_chart(rsn, rank, points, boss_points, skill_points)

        embed = discord.Embed(
            title=f"Rank Score - {rsn}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Rank", value=rank, inline=True)
        embed.add_field(name="Total Points", value=f"{points:,}", inline=True)
        embed.add_field(name="​", value="​", inline=True)
        if not stats_opt_out:
            embed.add_field(name="Boss Points", value=f"{boss_points:,}", inline=True)
            embed.add_field(name="Skill Points", value=f"{skill_points:,}", inline=True)
            embed.add_field(name="​", value="​", inline=True)
        else:
            embed.set_footer(text="Stats hidden (opt-out)")

        if chart_file:
            embed.set_image(url="attachment://rank_score.png")

        send_kwargs: dict = {"embed": embed}
        if chart_file:
            send_kwargs["file"] = chart_file

        await ticket.channel.send(**send_kwargs)

        ticket.record.metadata["rank_pull_done"] = True
        ticket.record.metadata["rank_pull_rsn"] = rsn
        await self._service.repo.update_ticket(
            self._ticket_id, metadata=ticket.record.metadata
        )

        set_primary = await _get_rank_pull_set_primary()
        if set_primary:
            creator_id = ticket.record.creator.id
            creator_member = self._service.guild.get_member(creator_id)
            if creator_member is None:
                try:
                    creator_member = await self._service.guild.fetch_member(creator_id)
                except discord.HTTPException:
                    creator_member = None
            if creator_member is not None:
                ok = await _set_primary_account(creator_member, rsn)
                if ok:
                    logger.info(
                        "Rank pull: set primary RSN {} for user {}", rsn, creator_id
                    )
                else:
                    logger.debug(
                        "Rank pull: skipped primary set for user {} (already has primary or RSN taken)",
                        creator_id,
                    )
            else:
                logger.warning(
                    "Rank pull: could not fetch creator member {} for primary set", creator_id
                )

        await interaction.followup.send("Rank score posted.", ephemeral=True)


class PullRankScoreButton(discord.ui.Button):
    """Staff button: opens RSN modal, posts rank score breakdown. One-shot per ticket."""

    def __init__(self, service: "TicketService") -> None:
        super().__init__(
            label="Pull Rank Score",
            style=discord.ButtonStyle.secondary,
            emoji="📊",
            custom_id="ticket_sticky_pull_rank_score",
        )
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return

        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "No active ticket found in this channel.", ephemeral=True
            )
            return

        if ticket.record.ticket_type not in _RANK_TICKET_TYPES:
            await interaction.response.send_message(
                "Rank score pull is only available on Join CC and Rank Up tickets.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member) or not any(
            team.is_member(interaction.user) for team in ticket.ticket_type.teams
        ):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return

        if ticket.record.metadata.get("rank_pull_done"):
            rsn = ticket.record.metadata.get("rank_pull_rsn", "unknown")
            await interaction.response.send_message(
                f"Rank score already pulled for this ticket (RSN: **{rsn}**).",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(RsnModal(self._service, ticket.ticket_id))

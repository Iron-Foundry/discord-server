"""Persistent party panel view and embed builder."""

from __future__ import annotations

import math
from datetime import timezone
from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from core.db.models import PartyDB
    from features.parties.service import PartyService

_VIBE_COLOUR = {
    "learning": 0x5865F2,
    "chill":    0x57F287,
    "sweat":    0xED4245,
}


# ── Overview embed (page 0) ───────────────────────────────────────────────────

def active_ping_content(parties: list[PartyDB]) -> str:
    """Return a space-separated string of role mentions for all pings in active
    parties.  Used as message *content* so Discord actually fires notifications.
    """
    ids = {rid for p in parties for rid in (p.ping_role_ids or [])}
    return " ".join(f"<@&{rid}>" for rid in ids) if ids else ""


def _build_overview_embed(
    parties: list[PartyDB],
    ping_roles: list[dict],
    total_pages: int,
    guild: discord.Guild,
) -> discord.Embed:
    embed = discord.Embed(
        title="⚔️ Iron Foundry — Parties",
        color=discord.Color.gold(),
    )

    # Only show roles that are actually used by a current active party
    active_ids = {rid for p in parties for rid in (p.ping_role_ids or [])}
    active_roles = [r for r in ping_roles if r["discord_role_id"] in active_ids]
    if active_roles:
        mentions = "  ".join(f"<@&{r['discord_role_id']}>" for r in active_roles)
        embed.description = f"**Active pings**\n{mentions}"
    else:
        embed.description = ""

    if not parties:
        nl = "\n\n" if embed.description else ""
        embed.description += f"{nl}No active parties — create one to get started!"
    else:
        lines: list[str] = []
        for i, party in enumerate(parties, 1):
            leader = party.leader_rsn or party.leader_username
            spots = f"{len(party.members)}/{party.max_size}"
            suffix = " *(Full)*" if party.status == "full" else ""
            sched = ""
            if party.scheduled_at:
                aware = (
                    party.scheduled_at
                    if party.scheduled_at.tzinfo
                    else party.scheduled_at.replace(tzinfo=timezone.utc)
                )
                sched = f" · <t:{int(aware.timestamp())}:R>"
            lines.append(
                f"`{i}` **{party.activity}**{suffix} — {leader} — {spots}{sched}"
            )
        pw = "party" if len(parties) == 1 else "parties"
        embed.add_field(
            name=f"Active & Upcoming {pw} ({len(parties)})",
            value="\n".join(lines),
            inline=False,
        )

    hint = "Use ▶ to browse party details" if total_pages > 1 else ""
    embed.set_footer(text=hint or "No parties yet")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


# ── Detail embed (pages 1…N) ──────────────────────────────────────────────────

def _build_detail_embed(
    party: PartyDB,
    index: int,
    total: int,
    guild: discord.Guild,
) -> discord.Embed:
    """Full-detail embed for a single party."""
    embed = discord.Embed(
        title=party.activity,
        description=party.description or "",
        color=_VIBE_COLOUR.get(party.vibe, discord.Color.gold().value),
    )

    status_label = "Full" if party.status == "full" else "Open"
    spots = f"{len(party.members)}/{party.max_size}"
    embed.add_field(name="Status", value=status_label, inline=True)
    embed.add_field(name="Vibe",   value=party.vibe.capitalize(), inline=True)
    embed.add_field(name="Spots",  value=spots, inline=True)

    leader_display = party.leader_rsn or party.leader_username
    embed.add_field(name="Leader", value=leader_display, inline=True)

    member_lines: list[str] = []
    for m in party.members:
        name = m.rsn or m.username
        if m.user_id == party.leader_id:
            name = f"👑 {name}"
        member_lines.append(name)
    embed.add_field(
        name="Members",
        value="\n".join(member_lines) or "—",
        inline=True,
    )

    embed.add_field(name="Hub Code", value=f"`{party.hub_code}`", inline=True)

    if party.scheduled_at:
        aware = (
            party.scheduled_at
            if party.scheduled_at.tzinfo
            else party.scheduled_at.replace(tzinfo=timezone.utc)
        )
        embed.add_field(
            name="Starts", value=f"<t:{int(aware.timestamp())}:R>", inline=True
        )

    embed.add_field(
        name="Expires",
        value=f"<t:{int(party.expires_at.timestamp())}:R>",
        inline=True,
    )

    if party.ping_role_ids:
        embed.add_field(
            name="Pinged",
            value=" ".join(f"<@&{rid}>" for rid in party.ping_role_ids),
            inline=False,
        )

    embed.set_footer(text=f"Party {index} of {total} · Use ◀ ▶ to browse")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


# ── Unified entry point ───────────────────────────────────────────────────────

def build_panel_embed(
    parties: list[PartyDB],
    ping_roles: list[dict],
    page: int,
    guild: discord.Guild,
) -> tuple[discord.Embed, int, int]:
    """Return (embed, clamped_page, total_pages).

    Page 0 = overview.  Pages 1…N = full details for parties[page-1].
    """
    total_pages = 1 + len(parties)
    page = max(0, min(page, total_pages - 1))

    if page == 0 or not parties:
        embed = _build_overview_embed(parties, ping_roles, total_pages, guild)
    else:
        embed = _build_detail_embed(parties[page - 1], page, len(parties), guild)

    return embed, page, total_pages


# ── Button components ─────────────────────────────────────────────────────────

class CreatePartyButton(discord.ui.Button["PartyPanelView"]):
    """Opens the party creation modal."""

    def __init__(self) -> None:
        super().__init__(
            label="Create Party",
            style=discord.ButtonStyle.primary,
            custom_id="party_panel_create",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Show the create-party modal."""
        from features.parties.views.create_flow import CreatePartyModal

        assert self.view is not None
        modal = CreatePartyModal(service=self.view.service)
        await interaction.response.send_modal(modal)


class JoinPartyButton(discord.ui.Button["PartyPanelView"]):
    """Opens an ephemeral select of open parties to join."""

    def __init__(self) -> None:
        super().__init__(
            label="Join a Party",
            style=discord.ButtonStyle.success,
            custom_id="party_panel_join",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        service = self.view.service
        user_id = str(interaction.user.id)

        parties = await service.repo.get_active_parties()
        open_parties = [p for p in parties if p.status == "open"]

        if not open_parties:
            await interaction.response.send_message(
                "No open parties right now. Create one!",
                ephemeral=True,
            )
            return

        view = _JoinSelectView(service=service, parties=open_parties)
        await interaction.response.send_message(
            "Select a party to join:",
            view=view,
            ephemeral=True,
        )


class DiscardPartyButton(discord.ui.Button["PartyPanelView"]):
    """Lets the leader discard their own active party."""

    def __init__(self) -> None:
        super().__init__(
            label="Discard My Party",
            style=discord.ButtonStyle.danger,
            custom_id="party_panel_discard",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Check leadership then confirm discard."""
        assert self.view is not None
        service = self.view.service
        user_id = str(interaction.user.id)
        party = await service.repo.get_leader_party(user_id)

        if not party:
            await interaction.response.send_message(
                "You don't have an active party to discard.",
                ephemeral=True,
            )
            return

        view = _DiscardConfirmView(service=service, party_id=party.id)
        await interaction.response.send_message(
            f"Discard **{party.activity}**? This cannot be undone.",
            view=view,
            ephemeral=True,
        )


class _BrowseDetailsButton(discord.ui.Button["PartyPanelView"]):
    """Opens an ephemeral per-party detail browser."""

    def __init__(self, *, has_parties: bool) -> None:
        super().__init__(
            label="Browse Details",
            style=discord.ButtonStyle.secondary,
            custom_id="party_panel_browse",
            disabled=not has_parties,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        service = self.view.service
        parties = await service.repo.get_active_parties()
        if not parties:
            await interaction.response.send_message(
                "No parties to browse.", ephemeral=True
            )
            return
        embed = _build_detail_embed(parties[0], 1, len(parties), service._guild)
        view = _EphemeralBrowserView(service=service, parties=parties, page=0)
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )


# ── Join select (ephemeral) ───────────────────────────────────────────────────

class _JoinSelectView(discord.ui.View):
    """Ephemeral select menu of open parties the user can join."""

    def __init__(
        self, service: PartyService, parties: list[PartyDB]
    ) -> None:
        super().__init__(timeout=60)
        self._service = service

        options = [
            discord.SelectOption(
                label=p.activity[:100],
                value=p.id,
                description=(
                    f"{len(p.members)}/{p.max_size} members"
                    + (f" · {p.vibe.capitalize()}" if p.vibe else "")
                )[:100],
            )
            for p in parties[:25]
        ]
        select = discord.ui.Select(
            placeholder="Choose a party…",
            options=options,
            custom_id="party_join_select",
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        party_id: str = interaction.data["values"][0]  # type: ignore[index]
        user = interaction.user
        user_id = str(user.id)

        rsn = await self._service.repo.get_user_rsn(user_id)
        try:
            party = await self._service.repo.add_member(
                party_id,
                user_id=user_id,
                username=user.display_name,
                rsn=rsn,
            )
        except ValueError:
            await interaction.response.edit_message(
                content="You're already in that party.",
                view=None,
            )
            return

        if not party:
            await interaction.response.edit_message(
                content="That party no longer exists or is closed.",
                view=None,
            )
            return

        await self._service.refresh_panel()

        await interaction.response.edit_message(
            content=(
                f"✅ Joined **{party.activity}**!\n"
                f"Hub code: `{party.hub_code}`\n"
                "Manage your slot at ironfoundry.cc/parties."
            ),
            view=None,
        )
        logger.info(
            "JoinSelect: {} joined party {} ({})",
            user,
            party.id,
            party.activity,
        )


# ── Ephemeral party browser ───────────────────────────────────────────────────

class _EphemeralBrowserView(discord.ui.View):
    """Ephemeral paginated view showing full party details, one party per page."""

    def __init__(
        self,
        service: PartyService,
        parties: list[PartyDB],
        page: int,
    ) -> None:
        super().__init__(timeout=120)
        self._service = service
        self._parties = parties
        self._page = page
        total = len(parties)

        # Row 0: navigation
        prev = discord.ui.Button(
            label="◀", style=discord.ButtonStyle.secondary,
            disabled=(page == 0), row=0,
        )
        prev.callback = self._on_prev
        self.add_item(prev)

        indicator = discord.ui.Button(
            label=f"Party {page + 1} / {total}",
            style=discord.ButtonStyle.secondary,
            disabled=True, row=0,
        )
        indicator.callback = lambda i: i.response.defer()  # type: ignore[attr-defined]
        self.add_item(indicator)

        nxt = discord.ui.Button(
            label="▶", style=discord.ButtonStyle.secondary,
            disabled=(page >= total - 1), row=0,
        )
        nxt.callback = self._on_next
        self.add_item(nxt)

        # Row 1: same "Join a Party" select as the main panel
        join = discord.ui.Button(
            label="Join a Party", style=discord.ButtonStyle.success, row=1,
        )
        join.callback = self._on_join
        self.add_item(join)

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        await self._navigate(interaction, self._page - 1)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        await self._navigate(interaction, self._page + 1)

    async def _navigate(
        self, interaction: discord.Interaction, page: int
    ) -> None:
        parties = await self._service.repo.get_active_parties()
        if not parties:
            await interaction.response.edit_message(
                content="No more active parties.", embed=None, view=None
            )
            return
        page = max(0, min(page, len(parties) - 1))
        embed = _build_detail_embed(
            parties[page], page + 1, len(parties), self._service._guild
        )
        await interaction.response.edit_message(
            embed=embed,
            view=_EphemeralBrowserView(self._service, parties, page),
        )

    async def _on_join(self, interaction: discord.Interaction) -> None:
        parties = await self._service.repo.get_active_parties()
        open_parties = [p for p in parties if p.status == "open"]
        if not open_parties:
            await interaction.response.send_message(
                "No open parties right now.", ephemeral=True
            )
            return
        view = _JoinSelectView(service=self._service, parties=open_parties)
        await interaction.response.send_message(
            "Select a party to join:", view=view, ephemeral=True
        )


# ── Main panel view ───────────────────────────────────────────────────────────

class PartyPanelView(discord.ui.View):
    """Persistent party panel view — always shows the overview page."""

    def __init__(
        self,
        service: PartyService,
        parties: list[PartyDB],
        ping_roles: list[dict],  # noqa: ARG002 — kept for call-site compat
        page: int,  # noqa: ARG002
        site_url: str,
    ) -> None:
        super().__init__(timeout=None)
        self.service = service

        # Row 0: action buttons
        self.add_item(CreatePartyButton())
        self.add_item(JoinPartyButton())
        self.add_item(DiscardPartyButton())

        # Row 1: browse ephemeral + website link
        self.add_item(_BrowseDetailsButton(has_parties=bool(parties)))
        self.add_item(
            discord.ui.Button(
                label="Iron Foundry Parties",
                url=f"{site_url}/parties",
                style=discord.ButtonStyle.link,
                row=1,
            )
        )


# ── Discard confirm ───────────────────────────────────────────────────────────

class _DiscardConfirmView(discord.ui.View):
    def __init__(self, service: PartyService, party_id: str) -> None:
        super().__init__(timeout=60)
        self._service = service
        self._party_id = party_id

    @discord.ui.button(label="Yes, Discard", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button  # noqa: ARG002
    ) -> None:
        """Close the party and refresh the panel."""
        await self._service.repo.close_party(self._party_id)
        await self._service.refresh_panel()
        await interaction.response.edit_message(
            content="Party discarded.", view=None
        )
        logger.info(
            "PartyPanel: {} discarded party {}",
            interaction.user,
            self._party_id,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button  # noqa: ARG002
    ) -> None:
        await interaction.response.edit_message(content="Cancelled.", view=None)

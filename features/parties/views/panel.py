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

PAGE_SIZE = 5
_VIBE_LABEL = {"learning": "Learning", "chill": "Chill", "sweat": "Sweat"}


# ── Embed builder ─────────────────────────────────────────────────────────────

def build_panel_embed(
    parties: list[PartyDB],
    page: int,
    guild: discord.Guild,
) -> tuple[discord.Embed, int, int]:
    """Build the party panel embed for the given page.

    Returns (embed, clamped_page, total_pages).
    """
    total = len(parties)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    page_parties = parties[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    embed = discord.Embed(
        title="⚔️ Iron Foundry — Parties",
        color=discord.Color.gold(),
    )

    if not page_parties:
        embed.description = (
            "No active parties right now. Create one to get started!"
        )
    else:
        embed.description = (
            "Create and join parties for clan content.\n"
            "Full party management is available on the website."
        )
        for party in page_parties:
            leader = party.leader_rsn or party.leader_username
            vibe = _VIBE_LABEL.get(party.vibe, party.vibe.capitalize())
            spots = f"{len(party.members)}/{party.max_size}"
            status = " *(Full)*" if party.status == "full" else ""

            lines: list[str] = [f"**{vibe}** · {spots} · Leader: **{leader}**"]

            if party.description:
                snippet = party.description[:80]
                if len(party.description) > 80:
                    snippet += "…"
                lines.append(snippet)

            if party.scheduled_at:
                aware = (
                    party.scheduled_at
                    if party.scheduled_at.tzinfo
                    else party.scheduled_at.replace(tzinfo=timezone.utc)
                )
                lines.append(f"Starts <t:{int(aware.timestamp())}:R>")

            exp_ts = int(party.expires_at.timestamp())
            lines.append(f"Expires <t:{exp_ts}:R>")

            embed.add_field(
                name=f"{party.activity}{status}",
                value="\n".join(lines),
                inline=False,
            )

    party_word = "party" if total == 1 else "parties"
    embed.set_footer(
        text=(
            f"Page {page + 1}/{total_pages} · "
            f"{total} active {party_word}"
        )
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

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


class _PrevPageButton(discord.ui.Button["PartyPanelView"]):
    def __init__(self, *, disabled: bool) -> None:
        super().__init__(
            label="◀",
            style=discord.ButtonStyle.secondary,
            custom_id="party_panel_prev",
            disabled=disabled,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.service.navigate(interaction, delta=-1)


class _NextPageButton(discord.ui.Button["PartyPanelView"]):
    def __init__(self, *, disabled: bool) -> None:
        super().__init__(
            label="▶",
            style=discord.ButtonStyle.secondary,
            custom_id="party_panel_next",
            disabled=disabled,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.service.navigate(interaction, delta=1)


class _PageIndicator(discord.ui.Button["PartyPanelView"]):
    def __init__(self, page: int, total: int) -> None:
        super().__init__(
            label=f"{page + 1} / {total}",
            style=discord.ButtonStyle.secondary,
            custom_id="party_panel_page",
            disabled=True,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()


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


# ── Main panel view ───────────────────────────────────────────────────────────

class PartyPanelView(discord.ui.View):
    """Persistent party panel view shown in the configured channel."""

    def __init__(
        self,
        service: PartyService,
        parties: list[PartyDB],
        page: int,
        site_url: str,
    ) -> None:
        super().__init__(timeout=None)
        self.service = service

        total_pages = max(1, math.ceil(len(parties) / PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))

        # Row 0: actions
        self.add_item(CreatePartyButton())
        self.add_item(JoinPartyButton())
        self.add_item(DiscardPartyButton())
        self.add_item(
            discord.ui.Button(
                label="Iron Foundry Parties",
                url=f"{site_url}/parties",
                style=discord.ButtonStyle.link,
                row=0,
            )
        )

        # Row 1: pagination (only when needed)
        if total_pages > 1:
            self.add_item(_PrevPageButton(disabled=page == 0))
            self.add_item(_PageIndicator(page, total_pages))
            self.add_item(_NextPageButton(disabled=page >= total_pages - 1))


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

"""Persistent party panel layout view (Components V2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from core.db.models import PartyDB
    from features.parties.service import PartyService

# Component budget: Container(1) + Header(1) + Sep(1) + N×[Section+Text+Btn](3N)
# + (N-1) inter-party Seps + overflow Sep+Text(2) + footer Sep(1) + Text(1)
# + ActionRow(1) + 3 Buttons(3) = 10 + 4N + 2 = 38 at N=7. Hard cap at 7.
_MAX_PARTY_SECTIONS = 7

# ── Party text builder ────────────────────────────────────────────────────────


def _build_party_text(party: PartyDB) -> str:
    status_suffix = " *(Full)*" if party.status == "full" else ""
    lines: list[str] = [f"**{party.activity}**{status_suffix}"]

    if party.description:
        lines.append(f"> {party.description}")

    spots = f"{len(party.members)}/{party.max_size}"
    ends_aware = (
        party.expires_at
        if party.expires_at.tzinfo
        else party.expires_at.replace(tzinfo=timezone.utc)
    )
    timing = f"Ends <t:{int(ends_aware.timestamp())}:R>"
    if party.scheduled_at:
        starts_aware = (
            party.scheduled_at
            if party.scheduled_at.tzinfo
            else party.scheduled_at.replace(tzinfo=timezone.utc)
        )
        timing = (
            f"Starts <t:{int(starts_aware.timestamp())}:R>"
            f" · Ends <t:{int(ends_aware.timestamp())}:R>"
        )
    lines.append(f"{party.vibe.capitalize()} · {spots} · {timing}")

    members: list[str] = []
    for m in party.members:
        name = m.rsn or m.username
        if m.user_id == party.leader_id:
            name = f"👑 {name}"
        members.append(name)
    if members:
        lines.append(" · ".join(members))

    return "\n".join(lines)


# ── Status layout (ephemeral final states) ────────────────────────────────────


class _StatusLayout(discord.ui.LayoutView):
    """Minimal ephemeral status/success/error message layout."""

    def __init__(self, content: str) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(content=content),
            )
        )


# ── Per-party join button ─────────────────────────────────────────────────────


class _PartyJoinButton(discord.ui.Button):
    """Direct join button for one party.

    Stores service reference directly - workaround for discord.py nested-view
    bug (#10335) where self.view may be None on deeply nested items.
    """

    def __init__(self, *, party_id: str, is_full: bool, service: PartyService) -> None:
        super().__init__(
            label="Full" if is_full else "Join",
            style=(
                discord.ButtonStyle.secondary
                if is_full
                else discord.ButtonStyle.success
            ),
            custom_id=f"party_direct_join_{party_id}",
            disabled=is_full,
        )
        self._party_id = party_id
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        # defer() without ephemeral=True sends DEFERRED_UPDATE_MESSAGE (type 6),
        # which acknowledges the component without touching the panel message.
        # followup.send(ephemeral=True) then delivers a private reply.
        await interaction.response.defer()

        user = interaction.user
        user_id = str(user.id)
        rsn = await self._service.repo.get_user_rsn(user_id)

        try:
            party = await self._service.repo.add_member(
                self._party_id,
                user_id=user_id,
                username=user.display_name,
                rsn=rsn,
            )
        except ValueError:
            await interaction.followup.send(
                view=_StatusLayout("You're already in that party."),
                ephemeral=True,
            )
            return

        if not party:
            await interaction.followup.send(
                view=_StatusLayout("That party no longer exists or is closed."),
                ephemeral=True,
            )
            return

        joiner_name = rsn or user.display_name
        await self._service.notify_members(
            party,
            f"**{joiner_name}** joined **{party.activity}**.\n"
            f"Spots: {len(party.members)}/{party.max_size}",
            exclude_user_id=user_id,
        )
        await self._service.refresh_panel()
        await interaction.followup.send(
            view=_StatusLayout(
                f"Joined **{party.activity}**!\n"
                f"Hub code: `{party.hub_code}`\n"
                "Manage your slot at ironfoundry.cc/parties."
            ),
            ephemeral=True,
        )
        logger.info(
            "PartyPanel: {} joined party {} ({})",
            user,
            party.id,
            party.activity,
        )


# ── Panel action buttons ──────────────────────────────────────────────────────


class CreatePartyButton(discord.ui.Button):
    """Opens the party creation modal."""

    def __init__(self, service: PartyService) -> None:
        super().__init__(
            label="Create Party",
            style=discord.ButtonStyle.primary,
            custom_id="party_panel_create",
        )
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        from features.parties.views.create_flow import CreatePartyModal

        await interaction.response.send_modal(CreatePartyModal(service=self._service))


class LeavePartyButton(discord.ui.Button):
    """Leave any active party; closes it if the user is the leader."""

    def __init__(self, service: PartyService) -> None:
        super().__init__(
            label="Leave Party",
            style=discord.ButtonStyle.danger,
            custom_id="party_panel_leave",
        )
        self._service = service

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        parties = await self._service.repo.get_user_active_parties(user_id)

        if not parties:
            await interaction.followup.send(
                view=_StatusLayout("You're not in any active party."),
                ephemeral=True,
            )
            return

        if len(parties) == 1:
            party = parties[0]
            await interaction.followup.send(
                view=_LeaveConfirmLayout(
                    service=self._service,
                    party=party,
                    user_id=user_id,
                ),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                view=_LeaveSelectLayout(
                    service=self._service,
                    parties=parties,
                    user_id=user_id,
                ),
                ephemeral=True,
            )


# ── Leave flows ───────────────────────────────────────────────────────────────


class _LeaveSelectLayout(discord.ui.LayoutView):
    """Party picker when user is in multiple parties (timeout=60s)."""

    def __init__(
        self,
        *,
        service: PartyService,
        parties: list[PartyDB],
        user_id: str,
    ) -> None:
        super().__init__(timeout=60)
        self._service = service
        self._user_id = user_id
        self._parties_by_id = {p.id: p for p in parties}

        options = [
            discord.SelectOption(
                label=p.activity[:100],
                value=p.id,
                description=(
                    f"{'Leader' if p.leader_id == user_id else 'Member'}"
                    f" · {len(p.members)}/{p.max_size}"
                )[:100],
            )
            for p in parties[:25]
        ]
        select = discord.ui.Select(
            placeholder="Choose a party to leave...",
            options=options,
            custom_id="party_leave_select",
        )
        select.callback = self._on_select

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(content="Select which party to leave:"),
                discord.ui.ActionRow(select),
            )
        )

    async def _on_select(self, interaction: discord.Interaction) -> None:
        party_id: str = interaction.data["values"][0]  # type: ignore[index]
        party = self._parties_by_id.get(party_id)
        if not party:
            await interaction.response.edit_message(
                view=_StatusLayout("That party no longer exists.")
            )
            return
        await interaction.response.edit_message(
            view=_LeaveConfirmLayout(
                service=self._service,
                party=party,
                user_id=self._user_id,
            )
        )


class _LeaveConfirmLayout(discord.ui.LayoutView):
    """Leave/abdicate/close confirmation (timeout=60s)."""

    def __init__(
        self,
        *,
        service: PartyService,
        party: PartyDB,
        user_id: str,
    ) -> None:
        super().__init__(timeout=60)
        self._service = service
        self._party_id = party.id
        self._user_id = user_id
        self._is_leader = party.leader_id == user_id
        self._next_leader_id: str | None = None
        self._next_leader_name: str | None = None
        leaving_member = next((m for m in party.members if m.user_id == user_id), None)
        self._user_display = (
            (leaving_member.rsn or leaving_member.username)
            if leaving_member
            else "Unknown"
        )

        if self._is_leader:
            others = [m for m in party.members if m.user_id != user_id]
            if others:
                next_m = min(others, key=lambda m: m.joined_at)
                self._next_leader_id = next_m.user_id
                self._next_leader_name = next_m.rsn or next_m.username
                prompt = (
                    f"Leave **{party.activity}**?\n"
                    f"Leadership will pass to **{self._next_leader_name}**."
                )
            else:
                prompt = (
                    f"Leave **{party.activity}**?\n"
                    "You're the only member - this will close the party."
                )
        else:
            prompt = f"Leave **{party.activity}**?"

        confirm_btn = discord.ui.Button(
            label="Yes, Leave",
            style=discord.ButtonStyle.danger,
            custom_id="party_leave_confirm",
        )
        confirm_btn.callback = self._on_confirm

        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="party_leave_cancel",
        )
        cancel_btn.callback = self._on_cancel

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(content=prompt),
                discord.ui.ActionRow(confirm_btn, cancel_btn),
                accent_colour=discord.Color.red(),
            )
        )

    async def _on_confirm(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self._is_leader:
            if self._next_leader_id:
                result = await self._service.repo.abdicate_and_leave(
                    self._party_id, self._user_id, self._next_leader_id
                )
                if result:
                    await self._service.notify_members(
                        result,
                        f"**{self._user_display}** has left **{result.activity}**.\n"
                        f"**{self._next_leader_name}** is now the party leader.",
                    )
                    msg = f"Left the party. **{self._next_leader_name}** is now the leader."
                else:
                    await self._service.repo.close_party(self._party_id)
                    msg = "Party closed."
            else:
                await self._service.repo.close_party(self._party_id)
                msg = "Party closed."
        else:
            result = await self._service.repo.remove_member(
                self._party_id, self._user_id
            )
            if result:
                await self._service.notify_members(
                    result,
                    f"**{self._user_display}** left **{result.activity}**.\n"
                    f"Spots: {len(result.members)}/{result.max_size}",
                )
            msg = "Left the party."
        await self._service.refresh_panel()
        await interaction.edit_original_response(view=_StatusLayout(msg))
        logger.info(
            "PartyPanel: {} left/abdicated/closed party {}",
            interaction.user,
            self._party_id,
        )

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=_StatusLayout("Cancelled."))


# ── Panel layout builder ──────────────────────────────────────────────────────


def build_panel_layout(
    parties: list[PartyDB],
    site_url: str,
    service: PartyService,
) -> PartyPanelLayoutView:
    """Build the persistent panel LayoutView from current party state."""
    return PartyPanelLayoutView(
        parties=parties,
        site_url=site_url,
        service=service,
    )


class PartyPanelLayoutView(discord.ui.LayoutView):
    """Persistent party panel - Components V2."""

    def __init__(
        self,
        *,
        parties: list[PartyDB],
        site_url: str,
        service: PartyService,
    ) -> None:
        super().__init__(timeout=None)

        shown = parties[:_MAX_PARTY_SECTIONS]
        overflow = max(0, len(parties) - _MAX_PARTY_SECTIONS)

        header = "## Iron Foundry - Parties"

        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(content=header),
            discord.ui.Separator(),
        ]

        if not shown:
            children.append(
                discord.ui.TextDisplay(
                    content=("No active parties - create one to get started!")
                )
            )
        else:
            for i, party in enumerate(shown):
                children.append(
                    discord.ui.Section(
                        discord.ui.TextDisplay(content=_build_party_text(party)),
                        accessory=_PartyJoinButton(
                            party_id=party.id,
                            is_full=party.status == "full",
                            service=service,
                        ),
                    )
                )
                if i < len(shown) - 1:
                    children.append(discord.ui.Separator())

            if overflow:
                children.append(discord.ui.Separator())
                children.append(
                    discord.ui.TextDisplay(
                        content=f"*...and {overflow} more - {site_url}/parties*"
                    )
                )

        now_ts = int(datetime.now(timezone.utc).timestamp())
        children.append(discord.ui.Separator())
        children.append(
            discord.ui.TextDisplay(content=f"-# Last updated <t:{now_ts}:R>")
        )
        children.append(
            discord.ui.ActionRow(
                CreatePartyButton(service),
                LeavePartyButton(service),
                discord.ui.Button(
                    label="Iron Foundry Parties",
                    url=f"{site_url}/parties",
                    style=discord.ButtonStyle.link,
                ),
            )
        )

        self.add_item(
            discord.ui.Container(
                *children,
                accent_colour=discord.Color.gold(),
            )
        )

"""Party creation modal and optional ping-role selection step."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from features.parties.service import PartyService

_DEFAULT_TTL = 4.0
_VALID_VIBES = {"chill", "learning", "sweat"}


def _parse_vibe(raw: str) -> str:
    v = raw.strip().lower()
    return v if v in _VALID_VIBES else "chill"


def _parse_size(raw: str) -> int:
    try:
        return max(1, min(100, int(raw.strip())))
    except ValueError:
        return 5


# ── Modal ─────────────────────────────────────────────────────────────────────

class CreatePartyModal(discord.ui.Modal, title="Create a Party"):
    """Collect party details from the user."""

    activity = discord.ui.TextInput(
        label="Activity",
        placeholder="e.g. Theatre of Blood",
        max_length=60,
        required=True,
    )
    description = discord.ui.TextInput(
        label="Description (optional)",
        placeholder="Requirements, notes…",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=False,
    )
    size = discord.ui.TextInput(
        label="Party Size",
        placeholder="e.g. 5",
        default="5",
        max_length=3,
        required=True,
    )
    vibe = discord.ui.TextInput(
        label="Vibe (chill / learning / sweat)",
        placeholder="chill",
        default="chill",
        max_length=10,
        required=False,
    )

    def __init__(self, service: PartyService) -> None:
        super().__init__()
        self._service = service

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """After the modal, either show ping-role select or create immediately."""
        ping_roles = await self._service.repo.get_ping_roles()

        activity = self.activity.value.strip()
        description = self.description.value.strip() or None
        max_size = _parse_size(self.size.value)
        vibe = _parse_vibe(self.vibe.value)

        if ping_roles:
            view = _PingSelectView(
                service=self._service,
                activity=activity,
                description=description,
                max_size=max_size,
                vibe=vibe,
                ping_roles=ping_roles,
            )
            await interaction.response.send_message(
                "Select roles to ping (optional):",
                view=view,
                ephemeral=True,
            )
        else:
            await _create_and_respond(
                interaction=interaction,
                service=self._service,
                activity=activity,
                description=description,
                max_size=max_size,
                vibe=vibe,
                ping_role_ids=[],
            )


# ── Ping-role select ──────────────────────────────────────────────────────────

class _PingSelectView(discord.ui.View):
    """Ephemeral follow-up letting the leader pick which roles to ping."""

    def __init__(
        self,
        *,
        service: PartyService,
        activity: str,
        description: str | None,
        max_size: int,
        vibe: str,
        ping_roles: list[dict],
    ) -> None:
        super().__init__(timeout=120)
        self._service = service
        self._activity = activity
        self._description = description
        self._max_size = max_size
        self._vibe = vibe
        self._selected: list[str] = []

        options = [
            discord.SelectOption(
                label=r.get("label", r["discord_role_id"]),
                value=r["discord_role_id"],
            )
            for r in ping_roles[:25]
        ]
        select = discord.ui.Select(
            placeholder="Choose roles to ping…",
            options=options,
            min_values=0,
            max_values=len(options),
            custom_id="party_ping_select",
        )
        select.callback = self._on_select
        self.add_item(select)

        confirm = discord.ui.Button(
            label="Create Party",
            style=discord.ButtonStyle.primary,
            custom_id="party_ping_confirm",
        )
        confirm.callback = self._on_confirm
        self.add_item(confirm)

    async def _on_select(
        self, interaction: discord.Interaction
    ) -> None:
        self._selected = interaction.data.get("values", [])  # type: ignore[assignment]
        await interaction.response.defer()

    async def _on_confirm(
        self, interaction: discord.Interaction
    ) -> None:
        await _create_and_respond(
            interaction=interaction,
            service=self._service,
            activity=self._activity,
            description=self._description,
            max_size=self._max_size,
            vibe=self._vibe,
            ping_role_ids=self._selected,
        )


# ── Shared creation helper ────────────────────────────────────────────────────

async def _create_and_respond(
    *,
    interaction: discord.Interaction,
    service: PartyService,
    activity: str,
    description: str | None,
    max_size: int,
    vibe: str,
    ping_role_ids: list[str],
) -> None:
    """Create the party in DB, refresh the panel, reply ephemerally."""
    user = interaction.user
    user_id = str(user.id)
    username = user.display_name

    # Look up RSN from DB
    rsn = await service.repo.get_user_rsn(user_id)

    party = await service.repo.create_party(
        leader_id=user_id,
        leader_username=username,
        leader_rsn=rsn,
        activity=activity,
        description=description,
        vibe=vibe,
        max_size=max_size,
        ttl_hours=_DEFAULT_TTL,
        ping_role_ids=ping_role_ids,
    )

    await service.refresh_panel()

    logger.info(
        "CreateFlow: {} created party {} ({})", user, party.id, activity
    )

    pings = (
        " ".join(f"<@&{rid}>" for rid in ping_role_ids)
        if ping_role_ids
        else ""
    )
    msg = (
        f"✅ **{activity}** created! Hub code: `{party.hub_code}`\n"
        "Manage your party fully at ironfoundry.cc/parties."
    )
    if pings:
        msg += f"\n{pings}"

    if interaction.response.is_done():
        await interaction.edit_original_response(content=msg, view=None)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

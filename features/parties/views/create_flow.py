"""Party creation modal."""

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
        placeholder="Requirements, notes...",
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
        activity = self.activity.value.strip()
        description = self.description.value.strip() or None
        max_size = _parse_size(self.size.value)
        vibe = _parse_vibe(self.vibe.value)

        await _create_and_respond(
            interaction=interaction,
            service=self._service,
            activity=activity,
            description=description,
            max_size=max_size,
            vibe=vibe,
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
) -> None:
    """Create the party in DB, refresh the panel, reply ephemerally."""
    from features.parties.views.panel import _StatusLayout

    user = interaction.user
    user_id = str(user.id)
    rsn = await service.repo.get_user_rsn(user_id)

    party = await service.repo.create_party(
        leader_id=user_id,
        leader_username=user.display_name,
        leader_rsn=rsn,
        activity=activity,
        description=description,
        vibe=vibe,
        max_size=max_size,
        ttl_hours=_DEFAULT_TTL,
    )

    await service.refresh_panel()
    logger.info("CreateFlow: {} created party {} ({})", user, party.id, activity)

    msg = (
        f"**{activity}** created! Hub code: `{party.hub_code}`\n"
        "Manage your party fully at ironfoundry.cc/parties."
    )
    await interaction.response.send_message(
        view=_StatusLayout(msg), ephemeral=True
    )

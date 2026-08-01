"""Staff verdict buttons, persistent across restarts via DynamicItem."""

from __future__ import annotations

import re
from typing import Any

import discord
from loguru import logger

from core.config import get_staff_role_ids

from . import api
from .layout import status_layout, verdict_layout

_TEMPLATE = r"tr_sub:(?P<event_id>\d+):(?P<thread_id>\d+):(?P<action>approve|reject)"


def custom_id(event_id: str, thread_id: int, action: str) -> str:
    return f"tr_sub:{event_id}:{thread_id}:{action}"


def verdict_buttons(event_id: str, thread_id: int) -> list[discord.ui.Button[Any]]:
    """Plain buttons carrying the ids; ``VerdictButton`` rebuilds itself on click."""
    return [
        discord.ui.Button(
            label="Approve",
            style=discord.ButtonStyle.success,
            custom_id=custom_id(event_id, thread_id, "approve"),
        ),
        discord.ui.Button(
            label="Reject",
            style=discord.ButtonStyle.danger,
            custom_id=custom_id(event_id, thread_id, "reject"),
        ),
    ]


class RejectModal(discord.ui.Modal, title="Reject Submission"):
    reason = discord.ui.TextInput(
        label="What is wrong with it?",
        style=discord.TextStyle.paragraph,
        placeholder="Missing the chat box, wrong account, item not visible...",
        max_length=500,
    )

    def __init__(self, event_id: str, thread_id: int) -> None:
        super().__init__()
        self._event_id = event_id
        self._thread_id = thread_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        await _submit_verdict(
            interaction,
            self._event_id,
            self._thread_id,
            "rejected",
            self.reason.value,
        )


class VerdictButton(
    discord.ui.DynamicItem[discord.ui.Button[Any]],
    template=_TEMPLATE,
):
    """Approve or reject every submission posted in this thread."""

    def __init__(self, event_id: str, thread_id: int, action: str) -> None:
        self.event_id = event_id
        self.thread_id = thread_id
        self.action = action
        approving = action == "approve"
        super().__init__(
            discord.ui.Button(
                label="Approve" if approving else "Reject",
                style=discord.ButtonStyle.success
                if approving
                else discord.ButtonStyle.danger,
                custom_id=custom_id(event_id, thread_id, action),
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
    ) -> VerdictButton:
        return cls(
            event_id=match["event_id"],
            thread_id=int(match["thread_id"]),
            action=match["action"],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _is_staff(interaction):
            await interaction.response.send_message(
                view=status_layout("Only event staff can review submissions."),
                ephemeral=True,
            )
            return
        if self.action == "reject":
            await interaction.response.send_modal(
                RejectModal(self.event_id, self.thread_id)
            )
            return
        await interaction.response.defer(thinking=True)
        await _submit_verdict(
            interaction, self.event_id, self.thread_id, "approved", None
        )


async def _is_staff(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    role_ids = await get_staff_role_ids()
    wanted = {rid for rid in role_ids.values() if rid}
    return any(role.id in wanted for role in member.roles)


async def _submit_verdict(
    interaction: discord.Interaction,
    event_id: str,
    thread_id: int,
    status: str,
    notes: str | None,
) -> None:
    try:
        result = await api.review(
            event_id, thread_id, status, interaction.user.id, notes
        )
    except api.ApiUnavailableError as exc:
        await interaction.followup.send(
            view=status_layout(f"Could not record that verdict: {exc}")
        )
        return
    logger.info(
        "tilerace submissions: thread {} {} by {}", thread_id, status, interaction.user
    )
    await interaction.followup.send(
        view=verdict_layout(status, interaction.user.mention, notes, result)
    )
    if isinstance(interaction.channel, discord.Thread):
        await interaction.channel.edit(archived=True, locked=status == "approved")

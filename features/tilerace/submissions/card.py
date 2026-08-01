"""The in-thread card: pick which requirements the screenshots prove, confirm."""

from __future__ import annotations

from typing import Any

import discord
from loguru import logger

from . import api, proof
from .layout import card_children, status_layout, submitted_layout
from .review import verdict_buttons

_SELECT_LIMIT = 25


class SubmissionCard(discord.ui.LayoutView):
    """Lives for the length of the submission, then is replaced by the verdict."""

    def __init__(
        self, context: dict[str, Any], author_id: int, captains_mention: str
    ) -> None:
        super().__init__(timeout=None)
        self._context = context
        self._author_id = author_id
        self._outstanding = [
            leaf for leaf in context.get("leaves") or [] if leaf.get("needed")
        ]
        self._chosen: list[str] = (
            [leaf["key"] for leaf in self._outstanding]
            if len(self._outstanding) == 1
            else []
        )

        children = card_children(context, captains_mention)
        children.append(discord.ui.Separator())
        if len(self._outstanding) > 1:
            children.append(discord.ui.ActionRow(self._build_select()))
        children.append(discord.ui.ActionRow(_ConfirmButton(self)))
        self.add_item(
            discord.ui.Container(*children, accent_colour=discord.Color.gold())
        )

    def _build_select(self) -> discord.ui.Select[Any]:
        select: discord.ui.Select[Any] = discord.ui.Select(
            placeholder="Which requirements do your screenshots prove?",
            min_values=1,
            max_values=min(len(self._outstanding), _SELECT_LIMIT),
            options=[
                discord.SelectOption(label=leaf["label"][:100], value=leaf["key"])
                for leaf in self._outstanding[:_SELECT_LIMIT]
            ],
        )
        select.callback = self._on_select
        return select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if not await self._is_author(interaction):
            return
        data: dict[str, Any] = interaction.data or {}  # type: ignore[assignment]
        self._chosen = list(data.get("values", []))
        await interaction.response.send_message(
            view=status_layout(f"Selected {len(self._chosen)} requirement(s)."),
            ephemeral=True,
        )

    async def _is_author(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self._author_id:
            return True
        await interaction.response.send_message(
            view=status_layout("Only the person who opened this thread can submit."),
            ephemeral=True,
        )
        return False

    async def confirm(self, interaction: discord.Interaction) -> None:
        if not await self._is_author(interaction):
            return
        if not self._chosen:
            await interaction.response.send_message(
                view=status_layout("Pick which requirements your proof covers first."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(thinking=True)
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.followup.send(
                view=status_layout("This can only be confirmed inside its thread.")
            )
            return

        urls = await proof.collect(thread, self._author_id)
        if not urls:
            await interaction.followup.send(
                view=status_layout(
                    "No screenshots found in this thread yet. Post your proof, "
                    "then press Confirm again."
                )
            )
            return
        try:
            result = await api.create(
                self._context["event_id"],
                self._author_id,
                int(self._context["path_position"]),
                self._chosen,
                urls,
                thread.id,
            )
        except api.ApiUnavailableError as exc:
            await interaction.followup.send(
                view=status_layout(f"Could not record that submission: {exc}")
            )
            return

        logger.info(
            "tilerace submissions: thread {} recorded {} leaf/leaves",
            thread.id,
            len(self._chosen),
        )
        await interaction.followup.send(
            view=submitted_layout(
                result,
                len(urls),
                verdict_buttons(self._context["event_id"], thread.id),
            )
        )


class _ConfirmButton(discord.ui.Button[Any]):
    def __init__(self, card: SubmissionCard) -> None:
        super().__init__(label="Confirm", style=discord.ButtonStyle.primary)
        self._card = card

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._card.confirm(interaction)

from __future__ import annotations

import discord

from core.common.ticket_types import TicketTypeId
from features.tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord
from features.tickets.views._layout_helpers import header_items


class SensitiveTicket(TicketTypeConfig):
    """
    Sensitive ticket - visible only to Senior Staff and Owners.
    No creation modal; the creator explains the issue in the channel directly.
    """

    def __init__(self, senior_staff_role_id: int, owner_role_id: int) -> None:
        self._teams = [
            TicketTeam(name="Senior Staff", role_id=senior_staff_role_id),
            TicketTeam(name="Owners", role_id=owner_role_id),
        ]
        self._db_overrides: dict = {}

    @property
    def identifier(self) -> str:
        return TicketTypeId.SENSITIVE.value

    @property
    def display_name(self) -> str:
        return self._db_overrides.get("display_name", "Sensitive")

    @property
    def description(self) -> str:
        return self._db_overrides.get("description", "For sensitive matters requiring Senior Staff or Owner attention.")

    @property
    def emoji(self) -> str:
        return self._db_overrides.get("emoji", "🔒")

    @property
    def color(self) -> discord.Color:
        return discord.Color.dark_red()

    @property
    def teams(self) -> list[TicketTeam]:
        return self._teams

    @property
    def channel_prefix(self) -> str:
        return "sensitive"

    @property
    def sensitive(self) -> bool:
        return True

    @property
    def category_name(self) -> str:
        return "Sensitive"

    def get_channel_permissions(
        self, guild: discord.Guild, creator: discord.Member
    ) -> dict[
        discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
    ]:
        overwrites: dict[
            discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
        ] = {}
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        overwrites[creator] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        )
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            )
        for team in self._teams:
            role = team.get_role(guild)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True,
                )
        return overwrites

    def build_create_layout(
        self,
        record: TicketRecord,
        *,
        header_attachment: str | None = None,
        rank_images: dict[str, str] | None = None,
    ) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                *header_items(header_attachment),
                discord.ui.TextDisplay(
                    content=(
                        f"## {self.emoji} Sensitive Ticket - #{record.ticket_id:04d}\n"
                        f"**Opened by:** <@{record.creator.id}>\n\n"
                        + (
                            self.welcome_text
                            or (
                                "This ticket is only visible to Senior Staff and Owners.\n"
                                "Please describe your concern below. All information shared here is strictly confidential.\n\n"
                                "-# No transcripts are saved. And no records of the ticket are visible to other staff."
                            )
                        )
                    )
                ),
                accent_colour=self.color,
            )
        )
        return view

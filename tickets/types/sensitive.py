import discord
from datetime import datetime, UTC

from common.ticket_types import TicketTypeId
from tickets.models.ticket import TicketTypeConfig, TicketTeam, TicketRecord


class SensitiveTicket(TicketTypeConfig):
    """
    Sensitive ticket — visible only to Senior Staff and Owners.
    No creation modal; the creator explains the issue in the channel directly.
    """

    def __init__(self, senior_staff_role_id: int, owner_role_id: int) -> None:
        self._teams = [
            TicketTeam(name="Senior Staff", role_id=senior_staff_role_id),
            TicketTeam(name="Owners", role_id=owner_role_id),
        ]

    @property
    def identifier(self) -> str:
        return TicketTypeId.SENSITIVE.value

    @property
    def display_name(self) -> str:
        return "Sensitive"

    @property
    def description(self) -> str:
        return "For sensitive matters requiring Senior Staff or Owner attention."

    @property
    def emoji(self) -> str:
        return "🔒"

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
    def category_name(self) -> str:
        return "Sensitive"

    def get_channel_permissions(
        self, guild: discord.Guild, creator: discord.Member
    ) -> dict[
        discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite
    ]:
        # Override: only Senior Staff, Owners, and the creator can see this channel
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

    def build_create_embed(self, record: TicketRecord) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.emoji} Sensitive Ticket — #{record.ticket_id:04d}",
            description=(
                "This ticket is only visible to Senior Staff and Owners.\n\n"
                "Please describe your concern below. All information shared here is strictly confidential."
            ),
            color=self.color,
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Opened by", value=f"<@{record.creator.id}>", inline=True)
        embed.set_footer(
            text="This ticket will auto-close after 24 hours of inactivity."
        )
        return embed

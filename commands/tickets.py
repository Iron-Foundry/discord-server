from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from commands.checks import handle_check_failure, is_senior_staff, is_staff
from commands.help_registry import HelpEntry, HelpGroup, HelpRegistry
from tickets.models.ticket import TicketStatus
from tickets.views.ticket_tools import CloseReasonModal

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService

_PERIOD_DAYS: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}

_PERIOD_CHOICES = [
    app_commands.Choice(name="Last 7 days", value="7d"),
    app_commands.Choice(name="Last 30 days", value="30d"),
    app_commands.Choice(name="Last 90 days", value="90d"),
    app_commands.Choice(name="All time", value="all"),
]


def _parse_period(period: str) -> datetime | None:
    days = _PERIOD_DAYS.get(period)
    return datetime.now(UTC) - timedelta(days=days) if days else None


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}h {m}m" if h else f"{m}m"


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the ticket and tickettype command groups."""
    registry.add_group(
        HelpGroup(
            name="ticket",
            description="Open, close, and manage support tickets",
            commands=[
                HelpEntry("/ticket open <type>", "Open a new ticket", "Everyone"),
                HelpEntry("/ticket close", "Close the current ticket", "Everyone"),
                HelpEntry(
                    "/ticket reopen <ticket_id>", "Reopen a closed ticket", "Everyone"
                ),
                HelpEntry("/ticket tools", "Spawn the moderator tools panel", "Staff"),
                HelpEntry("/ticket add <user>", "Add a user to this ticket", "Staff"),
                HelpEntry(
                    "/ticket remove <user>",
                    "Remove a user from this ticket",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket freeze",
                    "Freeze the 24-hour inactivity timeout",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket unfreeze",
                    "Unfreeze the 24-hour inactivity timeout",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket list <user>",
                    "List a user's recent tickets",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket transcript <ticket_id>",
                    "Get the transcript for a ticket (staff: any ticket; others: own only)",
                    "Everyone",
                ),
                HelpEntry(
                    "/ticket panel <channel>",
                    "Post the ticket panel to a channel",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/ticket stats [user] [period]",
                    "View handler statistics for a staff member",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket leaderboard [period]",
                    "Show top handlers ranked by tickets closed",
                    "Staff",
                ),
                HelpEntry(
                    "/ticket system [period]",
                    "View overall system stats: volumes, avg wait/response/resolution times",
                    "Staff",
                ),
            ],
        )
    )
    registry.add_group(
        HelpGroup(
            name="tickettype",
            description="Manage which ticket types are available",
            commands=[
                HelpEntry(
                    "/tickettype list",
                    "List all ticket types and their status",
                    "Everyone",
                ),
                HelpEntry(
                    "/tickettype enable <type>",
                    "Enable a ticket type",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/tickettype disable <type>",
                    "Disable a ticket type",
                    "Senior Staff",
                ),
            ],
        )
    )


class TicketGroup(
    app_commands.Group, name="ticket", description="Ticket management commands"
):
    def __init__(self, service: TicketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /ticket transcript <ticket_id>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="transcript", description="Get the transcript for a ticket"
    )
    @app_commands.describe(ticket_id="The ticket ID to fetch the transcript for")
    async def transcript(
        self, interaction: discord.Interaction, ticket_id: int
    ) -> None:
        from tickets.handlers.archive_channel import build_transcript_file

        await interaction.response.defer(ephemeral=True, thinking=True)

        staff_role_id_str = os.getenv("STAFF_ROLE_ID")
        caller_is_staff = (
            isinstance(interaction.user, discord.Member)
            and staff_role_id_str is not None
            and any(r.id == int(staff_role_id_str) for r in interaction.user.roles)
        )

        record = await self._service.repo.get_ticket(ticket_id)
        if not record or record.guild_id != self._service.guild.id:
            await interaction.followup.send(
                f"Ticket #{ticket_id:04d} not found.", ephemeral=True
            )
            return

        if not caller_is_staff and record.creator.id != interaction.user.id:
            await interaction.followup.send(
                "You can only view transcripts for your own tickets.", ephemeral=True
            )
            return

        ticket_type = self._service.type_registry.get(record.ticket_type)
        if ticket_type and ticket_type.sensitive:
            await interaction.followup.send(
                "Transcripts are not stored for this ticket type.", ephemeral=True
            )
            return

        if record.status == TicketStatus.OPEN:
            await interaction.followup.send(
                "This ticket is still open. Transcripts are saved when a ticket is closed.",
                ephemeral=True,
            )
            return

        saved_transcript = await self._service.repo.get_transcript(ticket_id)
        if not saved_transcript:
            await interaction.followup.send(
                f"No transcript found for ticket #{ticket_id:04d}.", ephemeral=True
            )
            return

        file = build_transcript_file(saved_transcript)
        await interaction.followup.send(
            f"Transcript for ticket **#{ticket_id:04d}**:",
            file=file,
            ephemeral=True,
        )

    @transcript.autocomplete("ticket_id")
    async def transcript_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        tickets = await self._service.get_closed_tickets_by_user(
            interaction.user.id, limit=25
        )
        return [
            app_commands.Choice(
                name=f"#{t.ticket_id:04d} — {t.ticket_type.replace('_', ' ').title()}",
                value=t.ticket_id,
            )
            for t in tickets
            if not current or current in str(t.ticket_id)
        ]

    # ------------------------------------------------------------------
    # /ticket panel <channel>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="panel", description="Post the ticket panel to a channel"
    )
    @app_commands.describe(channel="The channel to post the panel in")
    @is_senior_staff()
    async def panel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.post_panel(channel)
        await interaction.followup.send(
            f"Panel posted to {channel.mention}.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /ticket open <type>
    # ------------------------------------------------------------------

    @app_commands.command(name="open", description="Open a ticket")
    @app_commands.describe(ticket_type="The type of ticket to open")
    async def open(self, interaction: discord.Interaction, ticket_type: str) -> None:
        t = self._service.type_registry.get(ticket_type)
        if not t or not t.enabled:
            await interaction.response.send_message(
                "That ticket type is not available.", ephemeral=True
            )
            return

        modal = t.build_creation_modal(
            callback=lambda intr, meta: self._service.create_ticket(
                intr, ticket_type, meta
            )
        )
        if modal is not None:
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            ticket = await self._service.create_ticket(interaction, ticket_type, {})
            if ticket:
                await interaction.followup.send(
                    f"Ticket created: {ticket.channel.mention}", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "Failed to create ticket.", ephemeral=True
                )

    @open.autocomplete("ticket_type")
    async def open_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=t.display_name, value=t.identifier)
            for t in self._service.type_registry.get_enabled()
            if current.lower() in t.display_name.lower()
        ]

    # ------------------------------------------------------------------
    # /ticket close
    # ------------------------------------------------------------------

    @app_commands.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            CloseReasonModal(self._service, ticket.ticket_id)
        )

    # ------------------------------------------------------------------
    # /ticket tools
    # ------------------------------------------------------------------

    @app_commands.command(name="tools", description="Spawn the moderator tools panel")
    @is_staff()
    async def tools(self, interaction: discord.Interaction) -> None:
        await self._service.spawn_tools(interaction)

    # ------------------------------------------------------------------
    # /ticket add <user>
    # ------------------------------------------------------------------

    @app_commands.command(name="add", description="Add a user to this ticket")
    @app_commands.describe(user="The member to add")
    @is_staff()
    async def add(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        success = await self._service.add_user(ticket.ticket_id, user)
        if success:
            await interaction.response.send_message(
                f"Added {user.mention} to the ticket."
            )
        else:
            await interaction.response.send_message(
                "Failed to add user.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /ticket remove <user>
    # ------------------------------------------------------------------

    @app_commands.command(name="remove", description="Remove a user from this ticket")
    @app_commands.describe(user="The member to remove")
    @is_staff()
    async def remove(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        success = await self._service.remove_user(ticket.ticket_id, user)
        if success:
            await interaction.response.send_message(
                f"Removed {user.mention} from the ticket."
            )
        else:
            await interaction.response.send_message(
                "Failed to remove user.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /ticket freeze / unfreeze
    # ------------------------------------------------------------------

    @app_commands.command(
        name="freeze", description="Freeze the 24-hour inactivity timeout"
    )
    @is_staff()
    async def freeze(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        await self._service.freeze_timeout(ticket.ticket_id)
        await interaction.response.send_message(
            "⏸️ Timeout frozen — this ticket won't auto-close."
        )

    @app_commands.command(
        name="unfreeze", description="Unfreeze the 24-hour inactivity timeout"
    )
    @is_staff()
    async def unfreeze(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self._service.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        await self._service.unfreeze_timeout(ticket.ticket_id)
        await interaction.response.send_message(
            "▶️ Timeout unfrozen — 24-hour timer resumed."
        )

    # ------------------------------------------------------------------
    # /ticket reopen
    # ------------------------------------------------------------------

    @app_commands.command(name="reopen", description="Reopen a closed ticket")
    @app_commands.describe(ticket_id="The ticket ID to reopen")
    async def reopen(self, interaction: discord.Interaction, ticket_id: int) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        new_channel = await self._service.reopen_ticket(
            ticket_id=ticket_id,
            reopener=interaction.user,
        )
        if new_channel:
            await interaction.followup.send(
                f"Ticket #{ticket_id:04d} has been reopened in {new_channel.mention}.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Could not reopen ticket #{ticket_id:04d}. "
                "It may not exist or may not be closed.",
                ephemeral=True,
            )

    @reopen.autocomplete("ticket_id")
    async def reopen_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        tickets = await self._service.get_closed_tickets_by_user(
            interaction.user.id, limit=25
        )
        return [
            app_commands.Choice(
                name=f"#{t.ticket_id:04d} — {t.ticket_type.replace('_', ' ').title()}",
                value=t.ticket_id,
            )
            for t in tickets
            if not current or current in str(t.ticket_id)
        ]

    # ------------------------------------------------------------------
    # /ticket list <user>
    # ------------------------------------------------------------------

    @app_commands.command(name="list", description="List a user's recent tickets")
    @app_commands.describe(user="The member to look up")
    @is_staff()
    async def list_tickets(
        self, interaction: discord.Interaction, user: discord.Member
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        tickets = await self._service.get_recent_tickets_by_user(user.id, limit=10)

        embed = discord.Embed(
            title=f"Tickets — {user.display_name}",
            color=discord.Color.blurple(),
        )

        if not tickets:
            embed.description = "No tickets found for this user."
        else:
            for t in tickets:
                type_name = t.ticket_type.replace("_", " ").title()
                created = discord.utils.format_dt(t.created_at, style="d")
                embed.add_field(
                    name=f"#{t.ticket_id:04d} — {type_name}",
                    value=f"Status: **{t.status.value.capitalize()}** | Opened: {created}",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /ticket stats [user] [period]
    # ------------------------------------------------------------------

    @app_commands.command(
        name="stats", description="View handler statistics for a staff member"
    )
    @app_commands.describe(
        user="Staff member to view (defaults to you)",
        period="Time period to filter by",
    )
    @app_commands.choices(period=_PERIOD_CHOICES)
    @is_staff()
    async def stats(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        period: str = "all",
    ) -> None:
        from tickets.charts import build_stats_chart
        from tickets.views.stats import StatsView, _build_stats_embed

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            target = user if user is not None else interaction.user
            if not isinstance(target, discord.Member):
                await interaction.followup.send(
                    "Could not resolve the target member.", ephemeral=True
                )
                return

            since = _parse_period(period)
            handler_stats = await self._service.get_handler_stats(target.id, since)
            if handler_stats is None:
                await interaction.followup.send(
                    "No closed tickets found for this period.", ephemeral=True
                )
                return

            embed = _build_stats_embed(handler_stats, target.display_name, period)
            view = StatsView(self._service, target.id, target.display_name, period)
            chart = await build_stats_chart(handler_stats, target.display_name)
            if chart:
                await interaction.followup.send(
                    embed=embed, file=chart, view=view, ephemeral=True
                )
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Unhandled error in /ticket stats")
            await interaction.followup.send(
                "An error occurred while fetching stats.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /ticket leaderboard [period]
    # ------------------------------------------------------------------

    @app_commands.command(
        name="leaderboard", description="Show top handlers ranked by tickets closed"
    )
    @app_commands.describe(period="Time period to filter by")
    @app_commands.choices(period=_PERIOD_CHOICES)
    @is_staff()
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        period: str = "30d",
    ) -> None:
        from tickets.charts import build_leaderboard_chart
        from tickets.views.stats import LeaderboardView, _build_leaderboard_embed

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            since = _parse_period(period)
            entries = await self._service.get_leaderboard(since)
            names: dict[int, str] = {}
            if interaction.guild:
                names = {
                    e.staff_id: (
                        m.display_name
                        if (m := interaction.guild.get_member(e.staff_id)) is not None
                        else f"<@{e.staff_id}>"
                    )
                    for e in entries
                }

            embed = _build_leaderboard_embed(entries, names, period, "closed")
            view = LeaderboardView(self._service, period, "closed")
            chart = await build_leaderboard_chart(entries, names, "closed")
            if chart:
                await interaction.followup.send(
                    embed=embed, file=chart, view=view, ephemeral=True
                )
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Unhandled error in /ticket leaderboard")
            await interaction.followup.send(
                "An error occurred while fetching the leaderboard.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /ticket system [period]
    # ------------------------------------------------------------------

    @app_commands.command(
        name="system", description="View overall ticket system statistics"
    )
    @app_commands.describe(period="Time period to filter by")
    @app_commands.choices(period=_PERIOD_CHOICES)
    @is_staff()
    async def system(
        self,
        interaction: discord.Interaction,
        period: str = "all",
    ) -> None:
        from tickets.charts import build_system_chart
        from tickets.views.stats import SystemStatsView, _build_system_embed

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            since = _parse_period(period)
            stats = await self._service.get_system_stats(since)
            embed = _build_system_embed(stats, period)
            view = SystemStatsView(self._service, period)
            chart = await build_system_chart(stats)
            if chart:
                await interaction.followup.send(
                    embed=embed, file=chart, view=view, ephemeral=True
                )
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Unhandled error in /ticket system")
            await interaction.followup.send(
                "An error occurred while fetching system stats.", ephemeral=True
            )


class TicketTypeGroup(
    app_commands.Group, name="tickettype", description="Manage ticket types"
):
    def __init__(self, service: TicketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /tickettype enable <type>
    # ------------------------------------------------------------------

    @app_commands.command(name="enable", description="Enable a ticket type")
    @app_commands.describe(ticket_type="The ticket type to enable")
    @is_senior_staff()
    async def enable(self, interaction: discord.Interaction, ticket_type: str) -> None:
        t = self._service.type_registry.get(ticket_type)
        if not t:
            await interaction.response.send_message(
                "Unknown ticket type.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.enable_type(ticket_type)
        await interaction.followup.send(
            f"✅ **{t.display_name}** is now enabled.", ephemeral=True
        )

    @enable.autocomplete("ticket_type")
    async def enable_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=t.display_name, value=t.identifier)
            for t in self._service.type_registry.get_all()
            if not t.enabled and current.lower() in t.display_name.lower()
        ]

    # ------------------------------------------------------------------
    # /tickettype disable <type>
    # ------------------------------------------------------------------

    @app_commands.command(name="disable", description="Disable a ticket type")
    @app_commands.describe(ticket_type="The ticket type to disable")
    @is_senior_staff()
    async def disable(self, interaction: discord.Interaction, ticket_type: str) -> None:
        t = self._service.type_registry.get(ticket_type)
        if not t:
            await interaction.response.send_message(
                "Unknown ticket type.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.disable_type(ticket_type)
        await interaction.followup.send(
            f"⛔ **{t.display_name}** is now disabled.", ephemeral=True
        )

    @disable.autocomplete("ticket_type")
    async def disable_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=t.display_name, value=t.identifier)
            for t in self._service.type_registry.get_all()
            if t.enabled and current.lower() in t.display_name.lower()
        ]

    # ------------------------------------------------------------------
    # /tickettype list
    # ------------------------------------------------------------------

    @app_commands.command(
        name="list", description="List all ticket types and their status"
    )
    async def list_types(self, interaction: discord.Interaction) -> None:
        types = self._service.type_registry.get_all()
        if not types:
            await interaction.response.send_message(
                "No ticket types registered.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎫 Ticket Types",
            color=discord.Color.blurple(),
        )
        for t in types:
            status = "✅ Enabled" if t.enabled else "⛔ Disabled"
            embed.add_field(
                name=f"{t.emoji} {t.display_name}",
                value=f"`{t.identifier}` — {status}\n{t.description}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

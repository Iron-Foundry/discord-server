from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from commands.checks import handle_check_failure, is_senior_staff, is_staff
from commands.help_registry import HelpEntry, HelpGroup, HelpRegistry
from docket.models import (
    DocketPanelRecord,
    DonationEntry,
    EventEntry,
    PanelType,
    TOCEntry,
)

if TYPE_CHECKING:
    from docket.service import DocketService

_NOT_CONFIGURED = "Docket is not configured. Run `/docket setup <channel>` first."


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the docket command group."""
    registry.add_group(
        HelpGroup(
            name="docket",
            description="Manage the live community dashboard",
            commands=[
                HelpEntry(
                    "/docket setup <channel>",
                    "Configure the docket channel and post all panels",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/docket refresh [panel_type]",
                    "Force-refresh one or all API panels",
                    "Staff",
                ),
                HelpEntry(
                    "/docket reset",
                    "Delete and re-post all panels in order",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/docket events add <title> <description>",
                    "Add a clan event",
                    "Staff",
                ),
                HelpEntry(
                    "/docket events remove <event_id>",
                    "Remove a clan event",
                    "Staff",
                ),
                HelpEntry(
                    "/docket events list",
                    "List all events with their IDs",
                    "Staff",
                ),
                HelpEntry(
                    "/docket toc add <channel> <description>",
                    "Add a server guide entry",
                    "Staff",
                ),
                HelpEntry(
                    "/docket toc remove <entry_id>",
                    "Remove a server guide entry",
                    "Staff",
                ),
                HelpEntry(
                    "/docket toc move <entry_id> <position>",
                    "Reorder a server guide entry",
                    "Staff",
                ),
                HelpEntry(
                    "/docket toc list",
                    "List all TOC entries with their IDs",
                    "Staff",
                ),
                HelpEntry(
                    "/docket donations add <donor> <amount>",
                    "Record a clan donation",
                    "Staff",
                ),
                HelpEntry(
                    "/docket donations remove <entry_id>",
                    "Remove a donation entry",
                    "Staff",
                ),
                HelpEntry(
                    "/docket donations list",
                    "List all donations with their IDs",
                    "Staff",
                ),
            ],
        )
    )


# ---------------------------------------------------------------------------
# Autocomplete helpers
# ---------------------------------------------------------------------------


def _record_or_none(
    service: DocketService, panel_type: PanelType
) -> DocketPanelRecord | None:
    return service.get_record(panel_type)


async def _autocomplete_event_id(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    service: DocketService = interaction.namespace._service  # type: ignore[attr-defined]
    record = _record_or_none(service, PanelType.EVENTS)
    if not record:
        return []
    return [
        app_commands.Choice(name=e.title[:100], value=e.entry_id)
        for e in record.event_entries
        if current.lower() in e.title.lower()
    ][:25]


async def _autocomplete_toc_id(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    service: DocketService = interaction.namespace._service  # type: ignore[attr-defined]
    record = _record_or_none(service, PanelType.TOC)
    if not record:
        return []
    return [
        app_commands.Choice(
            name=f"<#{e.channel_id}> — {e.description}"[:100],
            value=e.entry_id,
        )
        for e in record.toc_entries
        if current.lower() in e.description.lower()
    ][:25]


async def _autocomplete_donation_id(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    service: DocketService = interaction.namespace._service  # type: ignore[attr-defined]
    record = _record_or_none(service, PanelType.DONATIONS)
    if not record:
        return []
    return [
        app_commands.Choice(name=e.donor_name[:100], value=e.entry_id)
        for e in record.donation_entries
        if current.lower() in e.donor_name.lower()
    ][:25]


# ---------------------------------------------------------------------------
# Confirm reset view
# ---------------------------------------------------------------------------


class _ConfirmResetView(discord.ui.View):
    def __init__(self, service: DocketService) -> None:
        super().__init__(timeout=60)
        self._service = service

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[_ConfirmResetView],
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._service.reset()
        await interaction.followup.send(
            "All docket panels have been reset and re-posted.", ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[_ConfirmResetView],
    ) -> None:
        await interaction.response.send_message("Reset cancelled.", ephemeral=True)
        self.stop()


# ---------------------------------------------------------------------------
# Events subgroup
# ---------------------------------------------------------------------------


class EventsGroup(app_commands.Group, name="events", description="Manage clan events"):
    """Subgroup for managing the events panel."""

    def __init__(self, service: DocketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    @app_commands.command(name="add", description="Add a clan event")
    @app_commands.describe(
        title="Event title",
        description="Event description",
        host="Host name or mention",
        starts="Start time (ISO 8601, e.g. 2025-01-01T20:00:00)",
        ends="End time (ISO 8601)",
        image_url="Optional banner image URL",
    )
    @is_staff()
    async def events_add(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        host: str = "",
        starts: str = "",
        ends: str = "",
        image_url: str = "",
    ) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return

        starts_at: datetime | None = None
        ends_at: datetime | None = None
        try:
            if starts:
                starts_at = datetime.fromisoformat(starts)
            if ends:
                ends_at = datetime.fromisoformat(ends)
        except ValueError as exc:
            await interaction.response.send_message(
                f"Invalid date format: {exc}", ephemeral=True
            )
            return

        entry = EventEntry(
            title=title,
            description=description,
            host=host,
            starts_at=starts_at,
            ends_at=ends_at,
            image_url=image_url or None,
        )
        await self._service.add_event(entry)
        await interaction.response.send_message(
            f"Event **{title}** added.", ephemeral=True
        )

    @app_commands.command(name="remove", description="Remove a clan event")
    @app_commands.describe(event_id="The event to remove")
    @app_commands.autocomplete(event_id=_autocomplete_event_id)
    @is_staff()
    async def events_remove(
        self, interaction: discord.Interaction, event_id: str
    ) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        removed = await self._service.remove_event(event_id)
        if removed:
            await interaction.response.send_message("Event removed.", ephemeral=True)
        else:
            await interaction.response.send_message("Event not found.", ephemeral=True)

    @app_commands.command(name="list", description="List all events with their IDs")
    @is_staff()
    async def events_list(self, interaction: discord.Interaction) -> None:
        record = self._service.get_record(PanelType.EVENTS)
        if not record or not record.event_entries:
            await interaction.response.send_message("No events found.", ephemeral=True)
            return
        lines = [f"`{e.entry_id}` — **{e.title}**" for e in record.event_entries]
        embed = discord.Embed(
            title="Events",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# TOC subgroup
# ---------------------------------------------------------------------------


class TOCGroup(app_commands.Group, name="toc", description="Manage the server guide"):
    """Subgroup for managing the TOC panel."""

    def __init__(self, service: DocketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    @app_commands.command(name="add", description="Add a server guide entry")
    @app_commands.describe(
        channel="The channel to link",
        description="Description of the channel",
        position="Display order (0-indexed, default: appended at end)",
    )
    @is_staff()
    async def toc_add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        description: str,
        position: int = -1,
    ) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        record = self._service.get_record(PanelType.TOC)
        if position < 0:
            position = len(record.toc_entries) if record else 0
        entry = TOCEntry(
            channel_id=channel.id, description=description, position=position
        )
        await self._service.add_toc_entry(entry)
        await interaction.response.send_message(
            f"TOC entry for {channel.mention} added.", ephemeral=True
        )

    @app_commands.command(name="remove", description="Remove a server guide entry")
    @app_commands.describe(entry_id="The entry to remove")
    @app_commands.autocomplete(entry_id=_autocomplete_toc_id)
    @is_staff()
    async def toc_remove(self, interaction: discord.Interaction, entry_id: str) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        removed = await self._service.remove_toc_entry(entry_id)
        if removed:
            await interaction.response.send_message(
                "TOC entry removed.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "TOC entry not found.", ephemeral=True
            )

    @app_commands.command(name="move", description="Reorder a server guide entry")
    @app_commands.describe(
        entry_id="The entry to move",
        new_position="New display position (0-indexed)",
    )
    @app_commands.autocomplete(entry_id=_autocomplete_toc_id)
    @is_staff()
    async def toc_move(
        self,
        interaction: discord.Interaction,
        entry_id: str,
        new_position: int,
    ) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        moved = await self._service.move_toc_entry(entry_id, new_position)
        if moved:
            await interaction.response.send_message("TOC entry moved.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "TOC entry not found.", ephemeral=True
            )

    @app_commands.command(
        name="list", description="List all TOC entries with their IDs"
    )
    @is_staff()
    async def toc_list(self, interaction: discord.Interaction) -> None:
        record = self._service.get_record(PanelType.TOC)
        if not record or not record.toc_entries:
            await interaction.response.send_message(
                "No TOC entries found.", ephemeral=True
            )
            return
        sorted_entries = sorted(record.toc_entries, key=lambda e: e.position)
        lines = [
            f"`{e.entry_id}` — <#{e.channel_id}> ({e.description})"
            for e in sorted_entries
        ]
        embed = discord.Embed(
            title="Server Guide Entries",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Donations subgroup
# ---------------------------------------------------------------------------


class DonationsGroup(
    app_commands.Group, name="donations", description="Manage clan donations"
):
    """Subgroup for managing the donations panel."""

    def __init__(self, service: DocketService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    @app_commands.command(name="add", description="Record a clan donation")
    @app_commands.describe(
        donor="Donor name or mention",
        amount='Amount donated (e.g. "50M GP", "Bond", "£10")',
        note="Optional note",
    )
    @is_staff()
    async def donations_add(
        self,
        interaction: discord.Interaction,
        donor: str,
        amount: str,
        note: str = "",
    ) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        entry = DonationEntry(donor_name=donor, amount=amount, note=note)
        await self._service.add_donation(entry)
        await interaction.response.send_message(
            f"Donation from **{donor}** recorded.", ephemeral=True
        )

    @app_commands.command(name="remove", description="Remove a donation entry")
    @app_commands.describe(entry_id="The donation to remove")
    @app_commands.autocomplete(entry_id=_autocomplete_donation_id)
    @is_staff()
    async def donations_remove(
        self, interaction: discord.Interaction, entry_id: str
    ) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        removed = await self._service.remove_donation(entry_id)
        if removed:
            await interaction.response.send_message("Donation removed.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "Donation not found.", ephemeral=True
            )

    @app_commands.command(name="list", description="List all donations with their IDs")
    @is_staff()
    async def donations_list(self, interaction: discord.Interaction) -> None:
        record = self._service.get_record(PanelType.DONATIONS)
        if not record or not record.donation_entries:
            await interaction.response.send_message(
                "No donations found.", ephemeral=True
            )
            return
        sorted_entries = sorted(
            record.donation_entries, key=lambda e: e.donated_at, reverse=True
        )
        lines = [
            f"`{e.entry_id}` — **{e.donor_name}** {e.amount}" for e in sorted_entries
        ]
        embed = discord.Embed(
            title="Donations",
            description="\n".join(lines[:25]),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Root /docket group
# ---------------------------------------------------------------------------


class DocketGroup(app_commands.Group, name="docket", description="Community dashboard"):
    """Root slash command group for managing the docket service."""

    def __init__(self, service: DocketService) -> None:
        super().__init__()
        self._service = service
        self.add_command(EventsGroup(service=service))
        self.add_command(TOCGroup(service=service))
        self.add_command(DonationsGroup(service=service))

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /docket setup <channel>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setup", description="Configure the docket channel and post all panels"
    )
    @app_commands.describe(channel="The channel to use as the docket dashboard")
    @is_senior_staff()
    async def setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if self._service.config:
            await self._service.setup(channel)
            await interaction.followup.send(
                f"Docket reconfigured in {channel.mention}.", ephemeral=True
            )
        else:
            await self._service.setup(channel)
            await interaction.followup.send(
                f"Docket set up in {channel.mention}. "
                f"{len(self._service._panels)} panels posted.",
                ephemeral=True,
            )

    # ------------------------------------------------------------------
    # /docket refresh [panel_type]
    # ------------------------------------------------------------------

    @app_commands.command(
        name="refresh",
        description="Force-refresh one or all API-backed panels",
    )
    @app_commands.describe(
        panel_type="Panel to refresh (omit to refresh all API panels)"
    )
    @app_commands.choices(
        panel_type=[
            app_commands.Choice(name="Achievements", value="achievements"),
        ]
    )
    @is_staff()
    async def refresh(
        self,
        interaction: discord.Interaction,
        panel_type: str = "",
    ) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        pt: PanelType | None = PanelType(panel_type) if panel_type else None
        ok = await self._service.force_refresh(pt)
        if ok:
            target = pt.value if pt else "all API"
            await interaction.followup.send(
                f"Refreshed {target} panel(s).", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Could not refresh — docket not configured.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /docket reset
    # ------------------------------------------------------------------

    @app_commands.command(
        name="reset",
        description="Delete and re-post all docket panels in order",
    )
    @is_senior_staff()
    async def reset(self, interaction: discord.Interaction) -> None:
        if not self._service.config:
            await interaction.response.send_message(_NOT_CONFIGURED, ephemeral=True)
            return
        view = _ConfirmResetView(service=self._service)
        await interaction.response.send_message(
            "This will delete and re-post all docket panels. Continue?",
            view=view,
            ephemeral=True,
        )

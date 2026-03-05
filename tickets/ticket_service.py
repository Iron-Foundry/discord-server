from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from typing import Any, cast

import discord
from loguru import logger

from tickets.handlers.archive_channel import ArchiveChannelTicketRepository
from tickets.handlers.database import MongoTicketRepository
from tickets.models.stats import HandlerStats, LeaderboardEntry, SystemStats
from tickets.models.ticket import (
    MemberSnapshot,
    ReopenEvent,
    Ticket,
    TicketRecord,
    TicketStatus,
    TicketTypeRegistry,
)
from tickets.models.transcript import (
    StaffAction,
    StaffActionType,
    Transcript,
    TranscriptHandler,
)

TICKET_TIMEOUT_SECONDS = 86_400  # 24 hours


class TicketService:
    """
    Central coordinator for the ticket system.

    Responsibilities:
    - Manage the panel embed and select menu
    - Create, close, and reopen tickets
    - Enforce per-user limits and 24-hr inactivity timeouts
    - Persist all state to MongoDB
    - Recover open tickets from the DB on bot restart
    - Dispatch to pluggable transcript handlers
    """

    def __init__(self, guild: discord.Guild, repo: MongoTicketRepository) -> None:
        self.guild = guild
        self.repo = repo
        self.type_registry = TicketTypeRegistry()
        # channel_id → Ticket
        self.active_tickets: dict[int, Ticket] = {}
        # ticket_id → asyncio.Task
        self._timeout_tasks: dict[int, asyncio.Task] = {}
        # name → (handler, enabled)
        self._transcript_handlers: dict[str, tuple[TranscriptHandler, bool]] = {
            "mongodb": (cast(TranscriptHandler, repo), True),
        }
        self._panel_channel: discord.TextChannel | None = None
        self._panel_message: discord.Message | None = None
        self._panel_category: discord.CategoryChannel | None = None
        self._closed_tickets: dict[int, Ticket] = {}

    # -------------------------------------------------------------------------
    # Startup — restart recovery
    # -------------------------------------------------------------------------

    async def initialize(self) -> None:
        """Set up MongoDB indexes. Safe to call before the guild cache is populated."""
        await self.repo.ensure_indexes()

    async def post_ready(self) -> None:
        """Register the archive handler and recover open tickets.

        Must be called from on_ready, after the guild cache is fully populated.
        """
        self.try_register_archive_handler()

        records = await self.repo.get_open_tickets(self.guild.id)
        now = datetime.now(UTC)
        recovered = 0

        for record in records:
            channel = self.guild.get_channel(record.channel_id)
            if not isinstance(channel, discord.TextChannel):
                logger.warning(
                    f"Ticket #{record.ticket_id}: channel {record.channel_id} not found, skipping"
                )
                continue

            creator = self.guild.get_member(record.creator.id)
            ticket_type = self.type_registry.get(record.ticket_type)
            if not ticket_type:
                logger.warning(
                    f"Ticket #{record.ticket_id}: unknown type '{record.ticket_type}', skipping"
                )
                continue

            ticket = Ticket.from_record(record, channel, ticket_type, creator)
            self.active_tickets[channel.id] = ticket
            recovered += 1

            if not record.timeout_frozen:
                elapsed = (
                    now - record.last_message_at.replace(tzinfo=UTC)
                ).total_seconds()
                remaining = max(0.0, TICKET_TIMEOUT_SECONDS - elapsed)
                if remaining == 0:
                    logger.info(
                        f"Ticket #{record.ticket_id} timed out while offline — closing"
                    )
                    asyncio.create_task(self._auto_close(ticket))
                else:
                    self._schedule_timeout(ticket, remaining)

        logger.info(f"TicketService: recovered {recovered} open tickets")

    # -------------------------------------------------------------------------
    # Panel
    # -------------------------------------------------------------------------

    async def post_panel(self, channel: discord.TextChannel) -> None:
        """Post (or re-post) the ticket panel in the given channel."""
        from tickets.views.panel import TicketPanelView, build_panel_embed

        self._panel_channel = channel
        self._panel_category = channel.category
        embed = build_panel_embed(self.guild)
        view = TicketPanelView(self)
        self._panel_message = await channel.send(embed=embed, view=view)
        logger.info(
            f"Panel posted to #{channel.name} "
            f"(category: {channel.category.name if channel.category else 'none'})"
        )

    async def refresh_panel(self) -> None:
        """Rebuild the panel select menu to reflect current enabled types."""
        if not self._panel_message:
            return
        from tickets.views.panel import TicketPanelView, build_panel_embed

        embed = build_panel_embed(self.guild)
        view = TicketPanelView(self)
        try:
            await self._panel_message.edit(embed=embed, view=view)
        except discord.NotFound:
            logger.warning("Panel message no longer exists; panel not refreshed")

    # -------------------------------------------------------------------------
    # Ticket lifecycle
    # -------------------------------------------------------------------------

    async def create_ticket(
        self,
        interaction: discord.Interaction,
        type_id: str,
        metadata: dict[str, Any],
    ) -> Ticket | None:
        """
        Create a new ticket channel and persist the record.
        Called from the panel select callback and from /ticket open.
        """
        ticket_type = self.type_registry.get(type_id)
        if not ticket_type or not ticket_type.enabled:
            logger.error(f"create_ticket: unknown or disabled type '{type_id}'")
            return None

        creator = interaction.user
        if not isinstance(creator, discord.Member):
            return None

        # Per-user open ticket limit
        existing = [
            t
            for t in self.active_tickets.values()
            if t.record.creator.id == creator.id and t.record.ticket_type == type_id
        ]
        if len(existing) >= ticket_type.max_open_per_user:
            logger.debug(
                f"create_ticket: {creator} already has {len(existing)} open "
                f"'{type_id}' ticket(s) — rejecting"
            )
            return None

        try:
            ticket_id = await self.repo.next_ticket_id()
            now = datetime.now(UTC)

            # Use the panel's category so all tickets land under the same category
            category = self._panel_category or await self._get_or_create_category(
                ticket_type.category_name
            )
            logger.debug(
                f"Ticket #{ticket_id}: using category '{category.name}' "
                f"({'panel' if self._panel_category else 'fallback'})"
            )
            channel_name = f"{ticket_type.channel_prefix}-{ticket_id:04d}"
            overwrites = ticket_type.get_channel_permissions(self.guild, creator)

            channel = await category.create_text_channel(
                name=channel_name, overwrites=overwrites
            )

            record = TicketRecord(
                ticket_id=ticket_id,
                guild_id=self.guild.id,
                channel_id=channel.id,
                creator=MemberSnapshot.from_member(creator),
                ticket_type=type_id,
                last_message_at=now,
                created_at=now,
                metadata=metadata,
            )

            transcript = Transcript(
                ticket_id=ticket_id,
                channel_id=channel.id,
                guild_id=self.guild.id,
                creator_id=creator.id,
                ticket_type=type_id,
                created_at=now,
            )

            ticket = Ticket(
                record=record, channel=channel, creator=creator, ticket_type=ticket_type
            )
            ticket.transcript = transcript

            self.active_tickets[channel.id] = ticket
            await self.repo.save_ticket(record)

            embed = ticket_type.build_create_embed(record)
            await channel.send(embed=embed)
            await ticket_type.on_created(record, channel)

            self._schedule_timeout(ticket, TICKET_TIMEOUT_SECONDS)

            logger.info(
                f"Ticket #{ticket_id} ({ticket_type.display_name}) created by {creator}"
            )
            return ticket

        except Exception as e:
            logger.exception(f"Failed to create ticket: {e}")
            return None

    async def close_ticket(
        self,
        ticket_id: int,
        closer: discord.Member,
        reason: str | None,
        note: str | None,
    ) -> bool:
        """Collect transcript, persist, DM the creator, then delete the channel."""
        ticket = self._get_by_ticket_id(ticket_id)
        if not ticket:
            logger.error(
                f"close_ticket: ticket #{ticket_id} not found in active tickets"
            )
            return False

        try:
            logger.info(
                f"Ticket #{ticket_id}: closing — closer={closer}, reason={reason!r}"
            )

            await self._cancel_timeout(ticket_id)

            # Collect message history (skipped for sensitive tickets)
            if ticket.ticket_type.sensitive:
                logger.info(
                    f"Ticket #{ticket_id}: sensitive — skipping transcript collection"
                )
                await ticket.close(closer, reason, note)
            else:
                logger.debug(f"Ticket #{ticket_id}: collecting message history")
                await ticket.collect_messages()
                await ticket.close(closer, reason, note)
                logger.debug(
                    f"Ticket #{ticket_id}: {len(ticket.transcript.entries)} messages collected"
                )

            # DM the ticket creator
            try:
                creator_user = await self.guild.fetch_member(ticket.record.creator.id)
                dm_lines = [f"**Your ticket #{ticket_id:04d} has been closed.**"]
                if reason:
                    dm_lines.append(f"\n**Reason:** {reason}")
                dm_lines.append(
                    "\nTo reopen, use `/ticket reopen` with your ticket ID."
                )
                dm_text = "\n".join(dm_lines)

                has_transcript = (
                    not ticket.ticket_type.sensitive and ticket.transcript.entries
                )
                if has_transcript:
                    from tickets.handlers.archive_channel import build_transcript_file

                    file = build_transcript_file(ticket.transcript)
                    await creator_user.send(dm_text, file=file)
                else:
                    await creator_user.send(dm_text)
                logger.debug(f"Ticket #{ticket_id}: close DM sent to {creator_user}")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.warning(
                    f"Ticket #{ticket_id}: could not DM creator "
                    f"{ticket.record.creator.id}: {e}"
                )

            # Save transcript via all active handlers (skipped for sensitive tickets)
            if not ticket.ticket_type.sensitive:
                logger.debug(f"Ticket #{ticket_id}: saving transcript")
                for handler in self._active_handlers():
                    await handler.save_transcript(ticket.transcript)

            # Persist status update
            await self.repo.update_ticket(
                ticket_id,
                status=TicketStatus.CLOSED.value,
                closed_at=ticket.record.closed_at.isoformat()
                if ticket.record.closed_at
                else None,
                closed_by_id=closer.id,
                close_reason=reason,
                staff_note=note,
            )

            # Delete the channel — transcript is already saved
            channel_name = ticket.channel.name
            try:
                await ticket.channel.delete(
                    reason=f"Ticket #{ticket_id:04d} closed by {closer.display_name}"
                )
                logger.debug(f"Ticket #{ticket_id}: channel #{channel_name} deleted")
            except discord.HTTPException as e:
                logger.warning(
                    f"Ticket #{ticket_id}: could not delete channel "
                    f"#{channel_name}: {e}"
                )

            # Move from active → closed tracking
            self.active_tickets.pop(ticket.channel.id, None)
            self._closed_tickets[ticket_id] = ticket

            logger.info(
                f"Ticket #{ticket_id} closed by {closer} (channel #{channel_name} deleted)"
            )
            return True

        except Exception as e:
            logger.exception(f"Failed to close ticket #{ticket_id}: {e}")
            return False

    async def reopen_ticket(
        self, ticket_id: int, reopener: discord.Member
    ) -> discord.TextChannel | None:
        """Create a new channel for a closed ticket and post the prior transcript."""
        # Get record from in-memory cache or DB
        cached = self._closed_tickets.get(ticket_id)
        if cached:
            record = cached.record
            ticket_type = cached.ticket_type
        else:
            record = await self.repo.get_ticket(ticket_id)
            if not record or record.status != TicketStatus.CLOSED:
                logger.error(
                    f"reopen_ticket: ticket #{ticket_id} not found or not closed"
                )
                return None
            ticket_type = self.type_registry.get(record.ticket_type)
            if not ticket_type:
                logger.error(
                    f"reopen_ticket: unknown type '{record.ticket_type}' "
                    f"for ticket #{ticket_id}"
                )
                return None

        try:
            logger.info(f"Ticket #{ticket_id}: reopening by {reopener}")

            # Create a new channel in the panel's category (original channel is deleted)
            category = self._panel_category or await self._get_or_create_category(
                ticket_type.category_name
            )
            channel_name = f"{ticket_type.channel_prefix}-{ticket_id:04d}"
            creator_member = self.guild.get_member(record.creator.id)
            overwrites = ticket_type.get_channel_permissions(
                self.guild, creator_member or reopener
            )
            new_channel = await category.create_text_channel(
                name=channel_name, overwrites=overwrites
            )
            logger.info(
                f"Ticket #{ticket_id}: new channel #{new_channel.name} "
                f"created under '{category.name}'"
            )

            # Post prior transcript file (skipped for sensitive tickets)
            if ticket_type.sensitive:
                logger.info(
                    f"Ticket #{ticket_id}: sensitive — skipping prior transcript post"
                )
            else:
                prior_transcript = await self.repo.get_transcript(ticket_id)
                if prior_transcript:
                    from tickets.handlers.archive_channel import build_transcript_file

                    file = build_transcript_file(prior_transcript)
                    await new_channel.send(
                        content="**Prior conversation transcript:**", file=file
                    )
                    logger.debug(f"Ticket #{ticket_id}: prior transcript posted")
                else:
                    logger.warning(
                        f"Ticket #{ticket_id}: no prior transcript found in DB"
                    )

            # Update the record in place
            now = datetime.now(UTC)
            record.status = TicketStatus.OPEN
            record.closed_at = None
            record.closed_by_id = None
            record.close_reason = None
            record.staff_note = None
            record.reopen_history.append(ReopenEvent(reopened_by_id=reopener.id))
            record.last_message_at = now
            record.channel_id = new_channel.id

            await self.repo.update_ticket(
                ticket_id,
                status=TicketStatus.OPEN.value,
                channel_id=new_channel.id,
                closed_at=None,
                closed_by_id=None,
                close_reason=None,
                staff_note=None,
                reopen_history=[
                    e.model_dump(mode="json") for e in record.reopen_history
                ],
                last_message_at=now.isoformat(),
            )

            # Post reopen embed
            reopen_embed = ticket_type.build_reopen_embed(record, reopener)
            await new_channel.send(embed=reopen_embed)

            # Register as active ticket
            new_ticket = Ticket.from_record(
                record, new_channel, ticket_type, creator_member
            )
            self.active_tickets[new_channel.id] = new_ticket
            self._closed_tickets.pop(ticket_id, None)

            self._schedule_timeout(new_ticket, TICKET_TIMEOUT_SECONDS)
            await ticket_type.on_reopened(record, reopener)

            logger.info(
                f"Ticket #{ticket_id} reopened by {reopener} in #{new_channel.name}"
            )
            return new_channel

        except Exception as e:
            logger.exception(f"Failed to reopen ticket #{ticket_id}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Ticket management
    # -------------------------------------------------------------------------

    async def add_user(self, ticket_id: int, member: discord.Member) -> bool:
        ticket = self._get_by_ticket_id(ticket_id)
        if not ticket:
            return False
        try:
            await ticket.channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
            )
            ticket.transcript.add_staff_action(
                StaffAction(
                    actor_id=member.id,
                    actor_name=str(member),
                    action=StaffActionType.ADDED_USER,
                    target_id=member.id,
                )
            )
            return True
        except discord.HTTPException as e:
            logger.error(f"add_user failed: {e}")
            return False

    async def remove_user(self, ticket_id: int, member: discord.Member) -> bool:
        ticket = self._get_by_ticket_id(ticket_id)
        if not ticket:
            return False
        try:
            await ticket.channel.set_permissions(member, overwrite=None)
            ticket.transcript.add_staff_action(
                StaffAction(
                    actor_id=member.id,
                    actor_name=str(member),
                    action=StaffActionType.REMOVED_USER,
                    target_id=member.id,
                )
            )
            return True
        except discord.HTTPException as e:
            logger.error(f"remove_user failed: {e}")
            return False

    async def freeze_timeout(self, ticket_id: int) -> bool:
        ticket = self._get_by_ticket_id(ticket_id)
        if not ticket:
            return False
        await self._cancel_timeout(ticket_id)
        ticket.record.timeout_frozen = True
        await self.repo.update_ticket(ticket_id, timeout_frozen=True)
        ticket.transcript.add_staff_action(
            StaffAction(actor_id=0, actor_name="System", action=StaffActionType.FROZE)
        )
        logger.info(f"Ticket #{ticket_id} timeout frozen")
        return True

    async def unfreeze_timeout(self, ticket_id: int) -> bool:
        ticket = self._get_by_ticket_id(ticket_id)
        if not ticket:
            return False
        ticket.record.timeout_frozen = False
        await self.repo.update_ticket(ticket_id, timeout_frozen=False)
        self._schedule_timeout(ticket, TICKET_TIMEOUT_SECONDS)
        ticket.transcript.add_staff_action(
            StaffAction(actor_id=0, actor_name="System", action=StaffActionType.UNFROZE)
        )
        logger.info(f"Ticket #{ticket_id} timeout unfrozen")
        return True

    async def spawn_tools(self, interaction: discord.Interaction) -> None:
        """Post the moderator tools view in the current ticket channel."""
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Cannot determine channel.", ephemeral=True
            )
            return
        ticket = self.get_ticket_by_channel(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message(
                "This command can only be used inside an active ticket channel.",
                ephemeral=True,
            )
            return
        from tickets.views.ticket_tools import TicketToolsView, build_tools_embed

        view = TicketToolsView(self, ticket.ticket_id)
        embed = build_tools_embed()
        await interaction.response.send_message(embed=embed, view=view)

    # -------------------------------------------------------------------------
    # Type management
    # -------------------------------------------------------------------------

    async def get_closed_tickets_by_user(
        self, user_id: int, limit: int = 25
    ) -> list[TicketRecord]:
        return await self.repo.get_tickets_by_user(
            self.guild.id, user_id, status=TicketStatus.CLOSED.value, limit=limit
        )

    async def get_recent_tickets_by_user(
        self, user_id: int, limit: int = 10
    ) -> list[TicketRecord]:
        return await self.repo.get_tickets_by_user(self.guild.id, user_id, limit=limit)

    async def get_handler_stats(
        self, staff_id: int, since: datetime | None
    ) -> HandlerStats | None:
        """Return aggregated handler stats for a staff member."""
        return await self.repo.get_handler_stats(self.guild.id, staff_id, since)

    async def get_system_stats(self, since: datetime | None) -> SystemStats:
        """Return aggregated system-wide ticket statistics."""
        return await self.repo.get_system_stats(self.guild.id, since)

    async def get_leaderboard(
        self, since: datetime | None, limit: int = 10, metric: str = "closed"
    ) -> list[LeaderboardEntry]:
        """Return the top handlers ranked by the given metric, excluding the bot."""
        bot_id = self.guild.me.id if self.guild.me else None
        exclude = [bot_id] if bot_id else []
        return await self.repo.get_leaderboard_stats(
            self.guild.id, since, limit, exclude, metric
        )

    # -------------------------------------------------------------------------
    # Transcript handler registry
    # -------------------------------------------------------------------------

    def register_handler(
        self, name: str, handler: TranscriptHandler, *, enabled: bool = True
    ) -> None:
        self._transcript_handlers[name] = (handler, enabled)

    def enable_handler(self, name: str) -> bool:
        if name not in self._transcript_handlers:
            return False
        handler, _ = self._transcript_handlers[name]
        self._transcript_handlers[name] = (handler, True)
        return True

    def disable_handler(self, name: str) -> bool:
        if name not in self._transcript_handlers:
            return False
        handler, _ = self._transcript_handlers[name]
        self._transcript_handlers[name] = (handler, False)
        return True

    def list_handlers(self) -> list[tuple[str, bool]]:
        return [
            (name, enabled) for name, (_, enabled) in self._transcript_handlers.items()
        ]

    def _active_handlers(self) -> list[TranscriptHandler]:
        return [h for h, enabled in self._transcript_handlers.values() if enabled]

    # -------------------------------------------------------------------------
    # Type management
    # -------------------------------------------------------------------------

    async def enable_type(self, identifier: str) -> None:
        self.type_registry.enable(identifier)
        await self.refresh_panel()

    async def disable_type(self, identifier: str) -> None:
        self.type_registry.disable(identifier)
        await self.refresh_panel()

    # -------------------------------------------------------------------------
    # Message hook (called from DiscordClient.on_message)
    # -------------------------------------------------------------------------

    async def handle_message(self, message: discord.Message) -> None:
        """Reset the 24-hr inactivity timer and update first_staff_response_at."""
        if not message.guild or message.author.bot:
            return

        ticket = self.active_tickets.get(message.channel.id)
        if not ticket or ticket.is_frozen:
            return

        now = datetime.now(UTC)
        ticket.record.last_message_at = now
        await self.repo.update_ticket(ticket.ticket_id, last_message_at=now.isoformat())

        # Track first staff response time and participation
        if isinstance(message.author, discord.Member) and any(
            team.is_member(message.author) for team in ticket.ticket_type.teams
        ):
            staff_id = message.author.id
            updates: dict[str, object] = {}
            if ticket.record.first_staff_response_at is None:
                ticket.record.first_staff_response_at = now
                updates["first_staff_response_at"] = now.isoformat()
            if staff_id not in ticket.record.participants:
                ticket.record.participants.append(staff_id)
                updates["participants"] = ticket.record.participants
            if updates:
                await self.repo.update_ticket(ticket.ticket_id, **updates)

        # Reset the 24-hr timer
        await self._cancel_timeout(ticket.ticket_id)
        self._schedule_timeout(ticket, TICKET_TIMEOUT_SECONDS)

    # -------------------------------------------------------------------------
    # Timeout internals
    # -------------------------------------------------------------------------

    def _schedule_timeout(self, ticket: Ticket, delay: float) -> None:
        task = asyncio.create_task(self._timeout_handler(ticket, delay))
        self._timeout_tasks[ticket.ticket_id] = task
        ticket._timeout_task = task

    async def _cancel_timeout(self, ticket_id: int) -> None:
        task = self._timeout_tasks.pop(ticket_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _timeout_handler(self, ticket: Ticket, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self._auto_close(ticket)
        except asyncio.CancelledError:
            pass

    async def _auto_close(self, ticket: Ticket) -> None:
        bot_member = self.guild.me
        if not bot_member:
            logger.error(
                f"Ticket #{ticket.ticket_id}: guild.me is None, cannot auto-close"
            )
            return
        logger.info(f"Ticket #{ticket.ticket_id} auto-closing due to inactivity")
        await self.close_ticket(
            ticket_id=ticket.ticket_id,
            closer=bot_member,
            reason="This ticket was automatically closed due to 24 hours of inactivity.",
            note="Auto-closed by timeout.",
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def get_ticket_by_channel(self, channel_id: int) -> Ticket | None:
        return self.active_tickets.get(channel_id)

    def _get_by_ticket_id(self, ticket_id: int) -> Ticket | None:
        for ticket in self.active_tickets.values():
            if ticket.ticket_id == ticket_id:
                return ticket
        return None

    def try_register_archive_handler(self) -> None:
        """Register the archive channel handler if the channel is now resolvable.

        Called after on_ready when the live guild cache has channels populated.
        """
        if "archive_channel" in self._transcript_handlers:
            return
        archive = self._get_archive_channel()
        if archive:
            self.register_handler(
                "archive_channel", ArchiveChannelTicketRepository(archive)
            )
            logger.info(f"ArchiveChannelTicketRepository registered → #{archive.name}")

    def _get_archive_channel(self) -> discord.TextChannel | None:
        from core.config import ConfigInterface, ConfigVars

        cfg = ConfigInterface()
        channel_id_str = cfg.get_variable(ConfigVars.ARCHIVE_CHANNEL_ID)
        if channel_id_str:
            ch = self.guild.get_channel(int(channel_id_str))
            return ch if isinstance(ch, discord.TextChannel) else None
        return None

    async def _get_or_create_category(
        self, name: str | None
    ) -> discord.CategoryChannel:
        target = name or "Tickets"
        category = discord.utils.get(self.guild.categories, name=target)
        if not category:
            category = await self.guild.create_category(target)
            logger.info(f"Created Discord category: {target}")
        return category

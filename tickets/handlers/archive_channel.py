import io
from datetime import datetime, UTC

import discord
from loguru import logger

from tickets.models.transcript import Transcript


def build_transcript_file(transcript: Transcript) -> discord.File:
    """Build a discord.File containing the plaintext transcript log."""
    buf = io.BytesIO(transcript.to_text().encode("utf-8"))
    return discord.File(buf, filename=f"ticket-{transcript.ticket_id:04d}.txt")


class ArchiveChannelTicketRepository:
    """
    TranscriptHandler that posts a summary embed and full message log
    to a Discord text channel when a ticket is closed.

    get_transcript is not supported — returns None.
    """

    def __init__(self, channel: discord.TextChannel) -> None:
        self._channel = channel

    async def save_transcript(self, transcript: Transcript) -> bool:
        try:
            embed = self._build_embed(transcript)
            file = self._build_file(transcript)
            await self._channel.send(embed=embed, file=file)
            return True
        except Exception as e:
            logger.error(
                f"ArchiveChannelTicketRepository: failed to post transcript #{transcript.ticket_id}: {e}"
            )
            return False

    async def get_transcript(self, ticket_id: int) -> None:
        return None

    # -------------------------------------------------------------------------

    def _build_embed(self, transcript: Transcript) -> discord.Embed:
        type_name = transcript.ticket_type.replace("_", " ").title()
        embed = discord.Embed(
            title=f"🗂️ Ticket Closed — #{transcript.ticket_id:04d}",
            color=discord.Color.greyple(),
            timestamp=datetime.now(UTC),
        )
        embed.add_field(name="Type", value=type_name, inline=True)
        embed.add_field(
            name="Creator", value=f"<@{transcript.creator_id}>", inline=True
        )
        embed.add_field(name="Duration", value=transcript.get_duration(), inline=True)
        embed.add_field(
            name="Messages", value=str(transcript.get_message_count()), inline=True
        )
        embed.add_field(
            name="Participants",
            value=str(len(transcript.get_unique_participants())),
            inline=True,
        )

        if transcript.close_reason:
            embed.add_field(
                name="Close Reason", value=transcript.close_reason, inline=False
            )
        if transcript.staff_note:
            embed.add_field(
                name="Staff Note", value=transcript.staff_note, inline=False
            )

        embed.set_footer(text=f"Channel ID: {transcript.channel_id}")
        return embed

    def _build_file(self, transcript: Transcript) -> discord.File:
        return build_transcript_file(transcript)

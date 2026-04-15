import io

import discord

from features.tickets.models.transcript import Transcript


def build_transcript_file(transcript: Transcript) -> discord.File:
    """Build a discord.File containing the plaintext transcript log."""
    buf = io.BytesIO(transcript.to_text().encode("utf-8"))
    return discord.File(buf, filename=f"ticket-{transcript.ticket_id:04d}.txt")

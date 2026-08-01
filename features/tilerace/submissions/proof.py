"""Turn the screenshots posted in a submission thread into permanent URLs.

Discord CDN links expire, and a submission has to stay reviewable on the
website long after the thread is archived, so every image is re-hosted the same
way ticket transcripts are.
"""

from __future__ import annotations

import os

import discord
import httpx
from loguru import logger

from core.uploadthing import upload_file
from features.tickets.image_utils import is_image, to_webp

_HISTORY_LIMIT = 50


async def collect(thread: discord.Thread, author_id: int) -> list[str]:
    """Re-host every image the submitter posted in the thread."""
    secret = os.getenv("UPLOADTHING_SECRET", "")
    if not secret:
        logger.warning("tilerace submissions: UPLOADTHING_SECRET not set")
        return []
    urls: list[str] = []
    index = 0
    async with httpx.AsyncClient(timeout=30) as http:
        async for message in thread.history(limit=_HISTORY_LIMIT, oldest_first=True):
            if message.author.id != author_id:
                continue
            for attachment in message.attachments:
                if not is_image(attachment.content_type, attachment.filename):
                    continue
                url = await _rehost(http, secret, thread.id, index, attachment)
                index += 1
                if url:
                    urls.append(url)
    return urls


async def _rehost(
    http: httpx.AsyncClient,
    secret: str,
    thread_id: int,
    index: int,
    attachment: discord.Attachment,
) -> str | None:
    filename = f"tilerace-{thread_id}-{index:03d}.webp"
    try:
        download = await http.get(attachment.url, follow_redirects=True)
        if download.status_code != 200:
            logger.warning(
                "tilerace submissions: download failed ({}) for {}",
                download.status_code,
                attachment.filename,
            )
            return None
        return await upload_file(
            http, secret, filename, to_webp(download.content), "image/webp"
        )
    except Exception as exc:
        logger.warning(
            "tilerace submissions: could not re-host {} - {}", attachment.filename, exc
        )
        return None

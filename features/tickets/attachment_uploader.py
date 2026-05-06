"""Uploads ticket attachment images to UploadThing, converting to WebP."""

import httpx
from loguru import logger

from core.uploadthing import upload_file
from features.tickets.image_utils import is_image, to_webp
from features.tickets.models.transcript import Transcript


async def upload_transcript_attachments(
    transcript: Transcript,
    http_client: httpx.AsyncClient,
    uploadthing_secret: str,
) -> int:
    """Download Discord CDN images, convert to WebP, upload to UploadThing.

    Mutates att.url, att.content_type, and att.filename in-place on success.
    Returns count of successfully replaced URLs.
    Never raises - one failure must not abort the ticket close.
    """
    replaced = 0
    img_index = 0

    for entry in transcript.entries:
        for att in entry.attachments:
            if not is_image(att.content_type, att.filename):
                continue

            webp_filename = (
                f"{transcript.ticket_type}-{transcript.ticket_id}-{img_index:03d}.webp"
            )
            img_index += 1

            try:
                dl = await http_client.get(att.url, follow_redirects=True)
                if dl.status_code != 200:
                    logger.warning(
                        f"Ticket #{transcript.ticket_id}: download failed "
                        f"({dl.status_code}) for {att.filename}, skipping"
                    )
                    continue

                webp_data = to_webp(dl.content)

                permanent_url = await upload_file(
                    http_client,
                    uploadthing_secret,
                    webp_filename,
                    webp_data,
                    "image/webp",
                )

                att.url = permanent_url
                att.content_type = "image/webp"
                att.filename = webp_filename
                replaced += 1
                logger.debug(
                    f"Ticket #{transcript.ticket_id}: uploaded {webp_filename} -> {permanent_url}"
                )

            except Exception as e:
                logger.warning(
                    f"Ticket #{transcript.ticket_id}: failed to upload "
                    f"{att.filename} as {webp_filename}: {e}"
                )

    return replaced

"""UploadThing upload wrapper using upyloadthing SDK."""

import io

import httpx
from upyloadthing import AsyncUTApi


async def upload_file(
    client: httpx.AsyncClient,
    secret: str,
    filename: str,
    data: bytes,
    content_type: str,
) -> str:
    """Upload bytes to UploadThing.

    Returns the permanent file URL.
    Raises on failure.
    """
    file_obj = io.BytesIO(data)
    file_obj.name = filename

    api = AsyncUTApi(token=secret)
    results = await api.upload_files(file_obj, acl="public-read", content_disposition="inline")

    if not results:
        raise RuntimeError("UploadThing returned no results")

    result = results[0] if isinstance(results, list) else results
    return result.url

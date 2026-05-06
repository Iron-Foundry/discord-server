"""UploadThing v7 REST API wrapper."""

import base64
import json
import os

import httpx


def _extract_api_key(secret: str) -> str:
    """Extract raw sk_live_... key from a base64-encoded UploadThing token or return as-is."""
    try:
        decoded = json.loads(base64.b64decode(secret + "=="))
        return decoded["apiKey"]
    except Exception:
        return secret


async def upload_file(
    client: httpx.AsyncClient,
    secret: str,
    filename: str,
    data: bytes,
    content_type: str,
) -> str:
    """Upload bytes to UploadThing v7 via prepareUpload + S3 multipart POST.

    Returns the permanent file URL (fileUrl from prepareUpload response).
    Raises httpx.HTTPStatusError on non-2xx from either request.
    """
    callback_url = os.getenv("FRONTEND_URL", "https://ironfoundry.cc").split(",")[0].strip()
    api_key = _extract_api_key(secret)

    # Step 1: prepare upload - get S3 presigned POST fields + permanent URL
    prepare_resp = await client.post(
        "https://api.uploadthing.com/v7/prepareUpload",
        headers={
            "x-uploadthing-api-key": api_key,
            "content-type": "application/json",
        },
        json={
            "files": [{"name": filename, "size": len(data)}],
            "callbackUrl": callback_url,
            "callbackSlug": "ticketImages",
            "contentDisposition": "inline",
            "acl": "public-read",
        },
    )
    prepare_resp.raise_for_status()

    raw = prepare_resp.json()
    # Response may be a list (one entry per file) or wrapped in {"data": [...]}
    if isinstance(raw, list):
        file_data = raw[0]
    elif "data" in raw:
        file_data = raw["data"][0]
    else:
        file_data = raw

    s3_url: str = file_data["url"]
    s3_fields: dict[str, str] = file_data["fields"]
    permanent_url: str = file_data["fileUrl"]

    # Step 2: POST to S3 as multipart/form-data
    # S3 presigned POST requires all signing fields before the file field
    multipart: list[tuple[str, tuple[None | str, bytes | str]]] = [
        (k, (None, v.encode())) for k, v in s3_fields.items()
    ]
    multipart.append(("file", (filename, data)))

    upload_resp = await client.post(s3_url, files=multipart)  # type: ignore[arg-type]
    upload_resp.raise_for_status()

    return permanent_url

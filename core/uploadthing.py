"""UploadThing v7 REST API wrapper."""

import httpx


async def upload_file(
    client: httpx.AsyncClient,
    secret: str,
    filename: str,
    data: bytes,
    content_type: str,
) -> str:
    """Upload bytes to UploadThing v7. Returns permanent file URL.

    Raises httpx.HTTPStatusError on non-2xx from either request.
    """
    # Step 1: request presigned upload URL
    presign_resp = await client.post(
        "https://api.uploadthing.com/v7/uploadFiles",
        headers={"x-uploadthing-api-key": secret},
        json={"files": [{"name": filename, "size": len(data), "type": content_type}]},
    )
    presign_resp.raise_for_status()
    file_data = presign_resp.json()["data"][0]

    presigned_url: str = file_data["url"]
    permanent_url: str = file_data["fileUrl"]

    # Step 2: PUT file bytes to presigned URL
    put_resp = await client.put(
        presigned_url,
        content=data,
        headers={"Content-Type": content_type},
    )
    put_resp.raise_for_status()

    return permanent_url

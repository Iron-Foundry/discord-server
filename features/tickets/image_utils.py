"""Image detection and WebP conversion for ticket attachments."""

import io

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".tiff"}
WEBP_QUALITY = 85


def is_image(content_type: str | None, filename: str) -> bool:
    """True if attachment is an image type we can convert and upload."""
    if content_type is not None:
        return content_type.startswith("image/") and content_type != "image/svg+xml"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return f".{ext}" in IMAGE_EXTENSIONS


def to_webp(data: bytes) -> bytes:
    """Convert image bytes to WebP using Pillow. Returns WebP bytes."""
    img = Image.open(io.BytesIO(data))

    buf = io.BytesIO()
    if getattr(img, "is_animated", False):
        # Preserve animated GIF frames
        frames = []
        try:
            while True:
                frames.append(img.copy().convert("RGBA"))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        frames[0].save(
            buf,
            format="WEBP",
            save_all=True,
            append_images=frames[1:],
            quality=WEBP_QUALITY,
            loop=0,
        )
    else:
        mode = "RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB"
        img.convert(mode).save(buf, format="WEBP", quality=WEBP_QUALITY)

    return buf.getvalue()

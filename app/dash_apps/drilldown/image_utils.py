# app/dash_apps/drilldown/image_utils.py
from PIL import Image
from io import BytesIO
MAX_IMAGE_SIZE = 25 * 1024  # 25 KB
MAX_DIMENSION = 800


def compress_to_webp(
    decoded_bytes: bytes,
    max_dimension: int = MAX_DIMENSION,
    max_size: int = MAX_IMAGE_SIZE,
) -> bytes | None:
    """Convert raw image bytes to WebP, stepping quality down until it
    fits under max_size. Returns None if even quality=10 doesn't fit."""
    img = Image.open(BytesIO(decoded_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((max_dimension, max_dimension))
    quality = 90
    while quality >= 10:
        buffer = BytesIO()
        img.save(
            buffer,
            format="WEBP",
            quality=quality,
            method=6,
            optimize=True,
        )
        size = buffer.tell()
        if size <= max_size:
            return buffer.getvalue()
        quality -= 5
    return None
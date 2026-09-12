# app/dash_apps/drilldown/image_utils.py
from PIL import Image
from io import BytesIO
from pathlib import Path
import time

MAX_IMAGE_SIZE = 50 * 1024  # 50 KB
MAX_DIMENSION  = 800


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


def cleanup_temp_images(max_age_hours: float = 2.0) -> int:
    """Remove stale WebP temp files from app/assets/default/ that are older
    than *max_age_hours*.  Returns the number of files removed.

    Temp files accumulate when a user opens an Add-New form, uploads/snaps an
    image, but then navigates away without submitting.  Without periodic
    cleanup those orphaned files grow unbounded.  This function is called at
    the start of every _save_captured_image() call so cleanup happens
    naturally during normal usage without a separate scheduler.
    """
    default_dir = Path("app/assets/default")
    if not default_dir.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    for f in default_dir.rglob("*.webp"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    if removed:
        print(f"🧹 Cleaned {removed} stale temp image(s) from {default_dir}")
    return removed
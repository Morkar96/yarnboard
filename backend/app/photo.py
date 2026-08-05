"""
Validation and normalization for manually-uploaded pattern photos.

Uploaded photos are stored as raw bytes directly in the `pattern` table
(see Pattern.photo_data in models.py) -- Render's web service has no
persistent disk across deploys, so there's nowhere else to put them without
standing up a separate object-storage service, which this app deliberately
doesn't have. To keep that bytea column from growing unboundedly, every
upload is re-encoded here rather than stored as-is: downscaled to a sane
maximum dimension and re-compressed as JPEG, which also happens to strip
all embedded metadata (EXIF, GPS) -- a privacy win, not just a size one.
"""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

# Raw upload cap, checked explicitly by the caller before this module ever
# runs -- tighter than the global 5MB MAX_CONTENT_LENGTH (config.py), since
# that cap's error message ("max 5MB") would be misleading for a photo.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

# Long-edge cap in pixels. Downscale only -- a smaller original is left as-is.
MAX_DIMENSION = 1600

JPEG_QUALITY = 82


class PhotoError(Exception):
    """Raised when uploaded bytes can't be read/processed as a photo."""


def process_upload(raw_bytes: bytes) -> bytes:
    """
    Validate that `raw_bytes` is a real image and return normalized JPEG
    bytes: downscaled to fit within MAX_DIMENSION on its longest edge,
    rotated upright per any EXIF orientation tag, converted to RGB, and
    re-encoded -- regardless of the original format (PNG, WEBP, ...).

    Raises PhotoError (with a user-facing message) if the bytes aren't a
    decodable image at all.
    """
    try:
        probe = Image.open(io.BytesIO(raw_bytes))
        probe.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise PhotoError("That file isn't a valid image.") from exc

    # verify() invalidates the image object for further use -- Pillow's own
    # documented idiom is to re-open before doing anything else with it.
    image = Image.open(io.BytesIO(raw_bytes))
    image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()

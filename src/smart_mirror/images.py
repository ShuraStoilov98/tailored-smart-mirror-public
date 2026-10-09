"""Bounded upload decoding, orientation normalization and metadata stripping."""
import base64
import binascii
import io
from pathlib import Path
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import InvalidImage

MAX_IMAGE_PIXELS = 12_000_000


def decode_and_save_image_from_request(body: dict, out_path: Path) -> bool:
    """Validate JPEG/PNG data, normalize to JPEG and discard EXIF metadata."""
    fields = [key for key in ("image_data_url", "image_base64") if key in body]
    if not fields:
        return False
    if len(fields) != 1 or not isinstance(body[fields[0]], str):
        raise InvalidImage("Provide one base64 image string.")
    encoded = body[fields[0]]
    if fields[0] == "image_data_url":
        header, separator, encoded = encoded.partition(",")
        if not separator or header not in {"data:image/jpeg;base64", "data:image/png;base64"}:
            raise InvalidImage("Only JPEG and PNG data URLs are accepted.")
    try:
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > 6 * 1024 * 1024:
            raise InvalidImage("Image is empty or too large.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise InvalidImage("Only JPEG and PNG images are accepted.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise InvalidImage("Image dimensions exceed the pixel limit.")
                image.load()
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                normalized.info.clear()
                normalized.save(out_path, format="JPEG", quality=90)
    except (binascii.Error, UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage("Invalid or oversized JPEG/PNG image.") from exc
    return True



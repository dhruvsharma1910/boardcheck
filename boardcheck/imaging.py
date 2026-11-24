"""Reading photos safely and putting them on a common footing."""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

try:  # iPhone photos. Optional: everything else works without it.
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

Image.MAX_IMAGE_PIXELS = 80_000_000
STORE_LONG = 2600   # largest side we keep
WORK_LONG = 1280    # largest side we compare at


class BadPhoto(ValueError):
    """The upload is not a photo we can read. The message is shown to the user."""


def load_image(data: bytes) -> np.ndarray:
    """Decode an upload to 8-bit BGR, upright, no larger than STORE_LONG."""
    if not data:
        raise BadPhoto("This file is empty.")
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)  # phones store rotation as a tag
        if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
            im = im.convert("RGBA")
            flat = Image.new("RGB", im.size, (255, 255, 255))
            flat.paste(im, mask=im.getchannel("A"))
            im = flat
        else:
            im = im.convert("RGB")
    except Image.DecompressionBombError:
        raise BadPhoto("This photo is too large. Use one under 80 megapixels.") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise BadPhoto("This file could not be read as a photo.") from None
    if min(im.size) < 64:
        raise BadPhoto("This photo is too small to check. Use one at least 64 pixels wide.")
    bgr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    return shrink(bgr, STORE_LONG)


def shrink(img: np.ndarray, long_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    s = long_side / max(h, w)
    if s >= 1:
        return img
    return cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)


def fit_long(img: np.ndarray, long_side: int) -> np.ndarray:
    """Resize, up or down, so the long side is exactly long_side."""
    h, w = img.shape[:2]
    s = long_side / max(h, w)
    size = (max(1, round(w * s)), max(1, round(h * s)))
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)


def to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def to_lab(img: np.ndarray) -> np.ndarray:
    """Float CIELAB: L in 0..100, a and b roughly -127..127."""
    f = np.clip(img.astype(np.float32) / 255.0, 0, 1)
    return cv2.cvtColor(f, cv2.COLOR_BGR2LAB)


def gradients(gray: np.ndarray, sigma: float = 1.0):
    g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), sigma)
    return cv2.Scharr(g, cv2.CV_32F, 1, 0) / 16, cv2.Scharr(g, cv2.CV_32F, 0, 1) / 16


def jpeg(img: np.ndarray, quality: int = 90) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()

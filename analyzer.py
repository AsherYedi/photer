"""Image quality analysis for PhotoSort.

Pure image-processing (no AI/ML model) using OpenCV. Given raw photo
bytes, this module measures:

  - sharpness   -> variance of the Laplacian (higher = sharper)
  - brightness  -> mean pixel intensity (0-255)
  - exposure    -> % of pixels clipped into pure shadows / highlights
  - resolution  -> width, height, megapixels

All processing happens in memory on the bytes passed in; nothing here
writes photos to disk.
"""
from typing import Dict, Tuple

import cv2
import numpy as np

# Histogram bins counted as "clipped" shadow/highlight pixels.
SHADOW_CLIP_BINS = 5
HIGHLIGHT_CLIP_BINS = 5

# Thumbnails are only for UI preview, never the full-resolution photo.
DEFAULT_THUMBNAIL_MAX_WIDTH = 320


def _decode(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image (unsupported or corrupt file).")
    return img


def compute_sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian. Low variance ~= flat/blurry edges."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def compute_brightness(gray: np.ndarray) -> float:
    """Mean pixel intensity, 0 (black) - 255 (white)."""
    return float(np.mean(gray))


def compute_exposure(gray: np.ndarray) -> Tuple[float, float]:
    """Percentage of pixels clipped at the shadow and highlight ends."""
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    total_pixels = gray.size
    shadow_clip_pct = float(hist[:SHADOW_CLIP_BINS].sum() / total_pixels * 100)
    highlight_clip_pct = float(hist[-HIGHLIGHT_CLIP_BINS:].sum() / total_pixels * 100)
    return shadow_clip_pct, highlight_clip_pct


def get_resolution(img: np.ndarray) -> Tuple[int, int]:
    height, width = img.shape[:2]
    return width, height


def analyze_image(image_bytes: bytes) -> Dict:
    """Run all quality measurements on a single photo.

    Returns a dict of raw metrics. Does not decide GOOD/REVIEW/POOR —
    that classification lives in scoring.py.
    """
    img = _decode(image_bytes)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    sharpness = compute_sharpness(gray)
    brightness = compute_brightness(gray)
    shadow_clip_pct, highlight_clip_pct = compute_exposure(gray)
    width, height = get_resolution(img)

    return {
        "sharpness": sharpness,
        "brightness": brightness,
        "shadow_clip_pct": shadow_clip_pct,
        "highlight_clip_pct": highlight_clip_pct,
        "width": width,
        "height": height,
        "megapixels": round((width * height) / 1_000_000, 2),
    }


def make_thumbnail(image_bytes: bytes, max_width: int = DEFAULT_THUMBNAIL_MAX_WIDTH) -> bytes:
    """Create a small in-memory JPEG thumbnail, for UI preview only.

    Keeping previews small (instead of caching full-resolution photos)
    is how the app avoids holding thousands of full photos in memory.
    """
    img = _decode(image_bytes)
    height, width = img.shape[:2]
    if width > max_width:
        scale = max_width / width
        img = cv2.resize(img, (max_width, max(1, int(height * scale))))
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise ValueError("Could not encode thumbnail.")
    return buf.tobytes()

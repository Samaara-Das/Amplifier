"""UGC authenticity post-processing pipeline.

Transforms "obviously AI" images into images that could plausibly be phone photos.
This is the single biggest quality lever — model choice matters less than post-processing.

Pipeline (in order):
1. Resize to platform-optimal dimensions
2. Slight desaturation (13%) — AI images are oversaturated
3. Warm/cool color cast — mimic phone camera processing
4. Film grain — diffusion models cannot generate authentic grain
5. Subtle vignetting — mimic phone lens characteristics
6. JPEG compression at quality 80 — introduce natural artifacts
7. EXIF metadata injection — mimic common phone cameras
"""

from __future__ import annotations

import logging
import random
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

# Platform-optimal dimensions (width x height)
PLATFORM_SIZES = {
    "x": (1200, 675),          # 16:9
    "linkedin": (1200, 627),   # ~1.91:1
    "facebook": (1200, 630),   # ~1.91:1
    "reddit": (1080, 1080),    # 1:1
    "instagram": (1080, 1080), # 1:1
    "tiktok": (1080, 1920),    # 9:16
}


def postprocess_for_ugc(
    image_path: str,
    output_path: str | None = None,
    platform: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Apply full UGC post-processing pipeline to an AI-generated image.

    Args:
        image_path: Path to the input image.
        output_path: Where to save (defaults to overwriting input).
        platform: If set, resize to platform-optimal dimensions.
        width/height: Override dimensions (takes precedence over platform).

    Returns: Path to the processed image.
    """
    if output_path is None:
        output_path = image_path

    img = Image.open(image_path).convert("RGB")

    # 1. Resize to target dimensions
    target_w, target_h = _get_target_size(img, platform, width, height)
    if (img.width, img.height) != (target_w, target_h):
        img = _smart_resize(img, target_w, target_h)

    # 2. Desaturation (13%) — AI images are too vibrant
    img = _desaturate(img, factor=0.87)

    # 3. Color cast — mimic phone camera processing
    arr = np.array(img, dtype=np.int16)
    arr = _apply_color_cast(arr)

    # 4. Film grain — models literally cannot generate this
    arr = _add_film_grain(arr, sigma=8)

    # 5. Vignetting — mimic phone lens characteristics
    arr = _add_vignette(arr, strength=0.25)

    img = Image.fromarray(arr.astype(np.uint8))

    # 6. Save as JPEG at quality 80 (introduces natural artifacts)
    img.save(output_path, "JPEG", quality=80)

    # 7. EXIF metadata injection
    _inject_exif(output_path)

    logger.info("Post-processed: %s → %s (%dx%d)", image_path, output_path, target_w, target_h)
    return output_path


def _get_target_size(
    img: Image.Image, platform: str | None, width: int | None, height: int | None
) -> tuple[int, int]:
    """Determine target dimensions."""
    if width and height:
        return width, height
    if platform and platform in PLATFORM_SIZES:
        return PLATFORM_SIZES[platform]
    return img.width, img.height


def _smart_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize with center crop to fill target dimensions (no black bars)."""
    src_ratio = img.width / img.height
    tgt_ratio = target_w / target_h

    if src_ratio > tgt_ratio:
        # Source is wider — crop sides
        new_h = img.height
        new_w = int(new_h * tgt_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, new_h))
    else:
        # Source is taller — crop top/bottom
        new_w = img.width
        new_h = int(new_w / tgt_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, new_w, top + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def _desaturate(img: Image.Image, factor: float = 0.87) -> Image.Image:
    """Reduce saturation. factor < 1.0 = less saturated."""
    enhancer = ImageEnhance.Color(img)
    return enhancer.enhance(factor)


def _apply_color_cast(arr: np.ndarray) -> np.ndarray:
    """Apply random warm or cool color cast (mimic phone camera processing)."""
    if random.random() < 0.5:
        # Warm cast
        arr[:, :, 0] = np.clip(arr[:, :, 0] + random.randint(3, 7), 0, 255)
        arr[:, :, 1] = np.clip(arr[:, :, 1] + random.randint(1, 4), 0, 255)
        arr[:, :, 2] = np.clip(arr[:, :, 2] - random.randint(1, 3), 0, 255)
    else:
        # Cool cast
        arr[:, :, 0] = np.clip(arr[:, :, 0] - random.randint(2, 5), 0, 255)
        arr[:, :, 1] = np.clip(arr[:, :, 1] + random.randint(1, 3), 0, 255)
        arr[:, :, 2] = np.clip(arr[:, :, 2] + random.randint(3, 7), 0, 255)
    return arr


def _add_film_grain(arr: np.ndarray, sigma: float = 8) -> np.ndarray:
    """Add Gaussian noise to simulate film grain.

    Diffusion models are architecturally designed to remove noise —
    they literally cannot generate authentic grain. This is the #1 tell.
    """
    noise = np.random.normal(0, sigma, arr.shape).astype(np.int16)
    return np.clip(arr + noise, 0, 255)


def _add_vignette(arr: np.ndarray, strength: float = 0.25) -> np.ndarray:
    """Apply radial vignetting (darken corners, mimic phone lens)."""
    rows, cols = arr.shape[:2]
    Y, X = np.ogrid[:rows, :cols]
    center_y, center_x = rows / 2, cols / 2
    radius = max(rows, cols) * 0.75
    dist_sq = (X - center_x) ** 2 + (Y - center_y) ** 2
    vignette = 1.0 - strength * (dist_sq / (radius ** 2))
    vignette = np.clip(vignette, 1.0 - strength, 1.0)
    result = arr.astype(np.float32) * vignette[:, :, np.newaxis]
    return np.clip(result, 0, 255).astype(np.int16)


def _inject_exif(image_path: str) -> None:
    """Inject EXIF metadata mimicking common phone cameras.

    Most social platforms strip EXIF on upload, but some don't — and it
    adds authenticity if the image is inspected before posting.
    """
    try:
        import piexif
    except ImportError:
        logger.debug("piexif not installed — skipping EXIF injection")
        return

    phones = [
        ("Apple", "iPhone 15 Pro", "17.4.1", (6900, 1000)),   # 6.9mm lens
        ("Apple", "iPhone 14", "17.3.1", (5100, 1000)),       # 5.1mm lens
        ("Samsung", "SM-S928B", "14", (6400, 1000)),           # Galaxy S24 Ultra
        ("Google", "Pixel 8 Pro", "14", (6900, 1000)),
        ("Apple", "iPhone 13", "17.2.1", (5100, 1000)),
    ]
    make, model, software, focal = random.choice(phones)

    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: make.encode(),
            piexif.ImageIFD.Model: model.encode(),
            piexif.ImageIFD.Software: software.encode(),
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: datetime.now().strftime("%Y:%m:%d %H:%M:%S").encode(),
            piexif.ExifIFD.FocalLength: focal,
            piexif.ExifIFD.ISOSpeedRatings: random.choice([50, 100, 200, 400, 640, 800]),
            piexif.ExifIFD.ExposureTime: (1, random.choice([60, 100, 125, 250, 500])),
        },
    }

    try:
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, image_path)
    except Exception as e:
        logger.debug("EXIF injection failed: %s", e)

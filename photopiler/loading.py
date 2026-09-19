"""Loading photos and normalizing them to a common working size."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo_inputs"
DEMO_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# Every photo is resized to about this many pixels, so photos from different
# sources (12 MP phone shots, small screenshots) come out at similar sizes.
WORK_AREA = 1_000_000

# Guard against "decompression bomb" uploads: Pillow refuses images over twice
# this many pixels (80 MP), comfortably above any real camera photo.
Image.MAX_IMAGE_PIXELS = 40_000_000


def load_photo(source) -> Image.Image:
    """Open an image file (path or file object) upright, as RGB, at WORK_AREA."""
    with Image.open(source) as img:
        # For JPEGs, let the decoder downscale by a power of two: much faster.
        scale = (WORK_AREA / (img.width * img.height)) ** 0.5
        if scale < 1:
            img.draft("RGB", (int(img.width * scale), int(img.height * scale)))
        img = ImageOps.exif_transpose(img)
        img = _flatten_to_rgb(img)
    return normalize_size(img)


def normalize_size(img: Image.Image, area: int = WORK_AREA) -> Image.Image:
    scale = (area / (img.width * img.height)) ** 0.5
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(size, Image.Resampling.LANCZOS)


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Convert to RGB, putting any transparent areas on white."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)
    return img.convert("RGB")


@lru_cache(maxsize=1)
def demo_photos() -> tuple[Image.Image, ...]:
    paths = sorted(p for p in DEMO_DIR.iterdir() if p.suffix.lower() in DEMO_EXTENSIONS)
    return tuple(load_photo(p) for p in paths)

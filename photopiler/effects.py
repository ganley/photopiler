"""Per-photo effects: borders, monochrome and aging."""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from .options import Age, Border, Tone

PAPER_COLOR = (246, 244, 238)  # slightly warm white, like photo paper

# Border widths as fractions of the photo's short side.
INSTAMATIC_BORDER = 0.05
POLAROID_SIDE_BORDER = 0.06
POLAROID_BOTTOM_BORDER = 0.22

OUTLINE_WIDTH = 2  # thin dark edge on borderless photos so overlaps stay visible
OUTLINE_COLOR = (0, 0, 0)

CONCRETE_BORDERS = [Border.NONE, Border.INSTAMATIC, Border.POLAROID]
CONCRETE_TONES = [Tone.COLOR, Tone.MONO]
CONCRETE_AGES = [Age.NONE, Age.LIGHT, Age.MEDIUM, Age.HEAVY]


@dataclass(frozen=True)
class AgingParams:
    saturation: float  # 1.0 = unchanged, 0.0 = grey
    sepia: float  # blend toward a warm sepia version: 0 = none, 1 = full sepia
    black: float  # faded blacks: darkest output level (0-255)
    white: float  # dulled whites: brightest output level (0-255)
    vignette: float  # how much the corners darken, 0-1
    grain: float  # standard deviation of the film-grain noise, in 0-255 levels


AGING = {
    Age.LIGHT: AgingParams(saturation=0.8, sepia=0.15, black=14, white=250, vignette=0.06, grain=6),
    Age.MEDIUM: AgingParams(saturation=0.6, sepia=0.35, black=28, white=242, vignette=0.12, grain=10),
    Age.HEAVY: AgingParams(saturation=0.35, sepia=0.6, black=45, white=232, vignette=0.2, grain=15),
}

# Film grain mixes two sizes of smooth noise: coarse grains (about GRAIN_SIZE
# pixels across) stay visible when the pile is viewed scaled down in a browser,
# and fine per-pixel grain adds texture. Its strength also varies in soft
# patches about GRAIN_PATCH_SIZE pixels across, so it isn't evenly spread.
GRAIN_SIZE = 2
GRAIN_FINE_WEIGHT = 0.5  # relative to the coarse grain
GRAIN_PATCH_SIZE = 60
GRAIN_PATCHINESS = 0.18  # 0 = even strength; 0.18 = roughly ±18% from patch to patch

# Sepia tone matrix (rows give output R, G, B), as in scratch/old.py but in RGB order.
SEPIA_MATRIX = np.array(
    [
        [0.393, 0.769, 0.189],
        [0.349, 0.686, 0.168],
        [0.272, 0.534, 0.131],
    ],
    dtype=np.float32,
)


def resolve_border(style: Border, rng) -> Border:
    return rng.choice(CONCRETE_BORDERS) if style is Border.RANDOM else style


def resolve_tone(tone: Tone, rng) -> Tone:
    return rng.choice(CONCRETE_TONES) if tone is Tone.RANDOM else tone


def resolve_age(age: Age, rng) -> Age:
    return rng.choice(CONCRETE_AGES) if age is Age.RANDOM else age


def age_photo(
    img: Image.Image, age: Age, noise_rng: np.random.Generator, grain_box=None
) -> Image.Image:
    """Make a print look old: fade and warm the colors, then add vignette and grain.

    Film grain belongs to the picture, not the paper, so it is only added inside
    `grain_box` (left, top, right, bottom), the photo area of a bordered print.
    Defaults to the whole image.
    """
    if age is Age.NONE:
        return img
    if age not in AGING:
        raise ValueError(f"cannot render age {age!r}")
    p = AGING[age]

    img = ImageEnhance.Color(img).enhance(p.saturation)
    pixels = np.asarray(img, dtype=np.float32)

    sepia = np.clip(pixels @ SEPIA_MATRIX.T, 0, 255)
    pixels = pixels * (1 - p.sepia) + sepia * p.sepia

    pixels = p.black + pixels * ((p.white - p.black) / 255)

    h, w = pixels.shape[:2]
    y, x = np.ogrid[-1 : 1 : h * 1j, -1 : 1 : w * 1j]
    falloff = 1 - p.vignette * (x * x + y * y) / 2  # 1 at the center, 1 - vignette at corners
    pixels *= falloff[..., None]

    # Luminance grain: the same noise on every channel, like film, not color speckle.
    left, top, right, bottom = grain_box or (0, 0, w, h)
    grain = film_grain(noise_rng, (bottom - top, right - left), p.grain)
    pixels[top:bottom, left:right] += grain[..., None]

    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")


def film_grain(rng: np.random.Generator, shape: tuple[int, int], sigma: float) -> np.ndarray:
    """Irregular film-like grain with standard deviation of about `sigma`."""
    coarse = smooth_noise(rng, shape, GRAIN_SIZE)
    fine = rng.standard_normal(shape, dtype=np.float32)
    grain = coarse + GRAIN_FINE_WEIGHT * fine
    grain /= grain.std() or 1
    strength = np.clip(1 + GRAIN_PATCHINESS * smooth_noise(rng, shape, GRAIN_PATCH_SIZE), 0.2, None)
    return sigma * grain * strength


def smooth_noise(rng: np.random.Generator, shape: tuple[int, int], feature: int) -> np.ndarray:
    """Noise with blobs about `feature` pixels across, scaled to standard deviation 1."""
    h, w = shape
    small = rng.standard_normal((h // feature + 2, w // feature + 2), dtype=np.float32)
    noise = np.asarray(Image.fromarray(small, "F").resize((w, h), Image.Resampling.BICUBIC))
    return noise / (noise.std() or 1)


def apply_tone(img: Image.Image, tone: Tone) -> Image.Image:
    """Convert to monochrome if asked. Returns RGB either way, so later effects
    (paper-colored borders, aging tints) can still add color."""
    if tone is Tone.MONO:
        return ImageOps.grayscale(img).convert("RGB")
    if tone is Tone.COLOR:
        return img
    raise ValueError(f"cannot render tone {tone!r}")


def border_widths(size: tuple[int, int], style: Border) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) border widths for a photo of `size`."""
    short = min(size)
    if style is Border.NONE:
        return (OUTLINE_WIDTH,) * 4
    if style is Border.INSTAMATIC:
        return (round(short * INSTAMATIC_BORDER),) * 4
    if style is Border.POLAROID:
        side = round(short * POLAROID_SIDE_BORDER)
        return (side, side, side, round(short * POLAROID_BOTTOM_BORDER))
    raise ValueError(f"cannot render border style {style!r}")


def bordered_size(size: tuple[int, int], style: Border) -> tuple[int, int]:
    left, top, right, bottom = border_widths(size, style)
    return size[0] + left + right, size[1] + top + bottom


def largest_print_size(size: tuple[int, int]) -> tuple[int, int]:
    """The biggest this photo can get with any border, in both dimensions."""
    sizes = [bordered_size(size, style) for style in CONCRETE_BORDERS]
    return max(w for w, _ in sizes), max(h for _, h in sizes)


def add_border(img: Image.Image, style: Border) -> Image.Image:
    fill = OUTLINE_COLOR if style is Border.NONE else PAPER_COLOR
    return ImageOps.expand(img, border=border_widths(img.size, style), fill=fill)

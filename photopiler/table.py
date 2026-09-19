"""The wooden tabletop under the pile, generated procedurally.

The wood is a function of table position, so it can be evaluated at exactly
the spot each output pixel sees, including through a tilted camera, where
the grain recedes in perspective along with the prints. Boards run away from
the camera, which keeps the grain from shimmering at low angles.

Distances are in print pixels (the photos' working resolution), so the wood
keeps the same scale relative to the prints whatever the canvas size.
"""

import math
from functools import lru_cache

import numpy as np
from PIL import Image

from . import camera

WOOD_LIGHT = np.array([188, 146, 100], np.float32)
WOOD_DARK = np.array([118, 80, 48], np.float32)

BOARD_WIDTH = 1300  # about 1.2 print widths
SEAM_WIDTH = 3
RING_SPACING = 70  # average distance between growth rings
RING_WOBBLE = 60  # how far the rings wander sideways
FIBER_STRENGTH = 0.12  # fine streaks along the grain
BLOTCH_STRENGTH = 0.08  # broad light and dark patches
BOARD_TONE_VARIATION = 0.1  # boards differ slightly in color

_LATTICE_SIZE = 256
_lattice = np.random.default_rng(20260919).standard_normal(
    (_LATTICE_SIZE, _LATTICE_SIZE)
).astype(np.float32)

ROWS_PER_CHUNK = 128  # evaluate in bands to keep memory use low


def surface(side: int, tilt: float, unit: float = 1.0) -> Image.Image:
    """The table as the camera sees it: a side × side RGB image.

    `unit` is how many output pixels one print pixel covers overhead (less
    than 1 when the canvas size cap has shrunk the prints).
    """
    # The table doesn't depend on the seed or the photos, so shuffling and
    # style changes reuse it. Copy, since the caller draws on the result.
    return _cached_surface(side, round(tilt, 3), round(unit, 6)).copy()


@lru_cache(maxsize=4)  # about 12 MB each for a 2000 px table
def _cached_surface(side: int, tilt: float, unit: float) -> Image.Image:
    out = np.empty((side, side, 3), np.uint8)
    xs = np.arange(side, dtype=np.float32) + 0.5
    for top in range(0, side, ROWS_PER_CHUNK):
        ys = np.arange(top, min(side, top + ROWS_PER_CHUNK), dtype=np.float32) + 0.5
        x, y = np.meshgrid(xs, ys)
        tx, ty = _table_coords(side, tilt, x, y)
        out[top : top + len(ys)] = wood(tx / unit, ty / unit)
    return Image.fromarray(out, "RGB")


def _table_coords(side, tilt, x, y):
    """Vectorized camera.table_point."""
    if tilt <= 0:
        return x, y
    half, cos_t, k, zoom = camera._params(side, tilt)
    xc, yc = x - half, y - half
    d = 1 + k * yc
    return half + xc / (zoom * d), half + yc / (zoom * cos_t * d)


def wood(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """RGB wood color (uint8, shape (..., 3)) at table positions x, y."""
    board = np.floor(x / BOARD_WIDTH)
    across = x - board * BOARD_WIDTH  # position across the board
    shift = _lattice[(board.astype(np.int64) * 37) % _LATTICE_SIZE, 11] * 5000  # per-board offset

    # Growth rings: wavy lines running along the board, shaped so that thin
    # dark lines sit on lighter wood.
    wobble = _noise(x / 400, (y + shift) / 2500) * RING_WOBBLE
    # Irregular spacing: distort the ring phase at two scales, so rings bunch
    # up and spread out rather than repeating evenly.
    phase = (
        (across + wobble) / RING_SPACING
        + 1.2 * _noise(x / 180, (y + shift) / 2500)
        + 0.5 * _noise(x / 60 + 30, (y + shift) / 900)
        + _noise(board * 3.1, 0) * 10
    )
    # Some rings are strong, some faint.
    ring_strength = np.clip(0.6 + 0.5 * _noise(x / 250 + 7, (y + shift) / 4000), 0.1, 1)
    rings = ring_strength * (0.5 + 0.5 * np.sin(2 * math.pi * phase)) ** 4

    fibers = _noise(x / 2.5, (y + shift * 3) / 70) * FIBER_STRENGTH
    blotches = _noise((x + 900) / 600, (y + shift) / 800) * BLOTCH_STRENGTH
    board_tone = _lattice[(board.astype(np.int64) * 53) % _LATTICE_SIZE, 97] * BOARD_TONE_VARIATION

    darkness = np.clip(0.3 + 0.55 * rings + fibers + blotches + board_tone, 0, 1)
    seam = (across < SEAM_WIDTH) | (across > BOARD_WIDTH - SEAM_WIDTH)
    darkness = np.where(seam, np.minimum(1, darkness + 0.5), darkness)

    color = WOOD_LIGHT + (WOOD_DARK - WOOD_LIGHT) * darkness[..., None]
    return np.clip(color, 0, 255).astype(np.uint8)


def _noise(u, v):
    """Smooth value noise: bilinear, smoothstepped interpolation of a random
    lattice, tiling every _LATTICE_SIZE units. Roughly unit variance."""
    u = np.asarray(u, np.float32)
    v = np.asarray(v, np.float32)
    iu, iv = np.floor(u), np.floor(v)
    fu, fv = u - iu, v - iv
    fu = fu * fu * (3 - 2 * fu)
    fv = fv * fv * (3 - 2 * fv)
    i0 = iu.astype(np.int64) % _LATTICE_SIZE
    j0 = iv.astype(np.int64) % _LATTICE_SIZE
    i1 = (i0 + 1) % _LATTICE_SIZE
    j1 = (j0 + 1) % _LATTICE_SIZE
    top = _lattice[j0, i0] * (1 - fu) + _lattice[j0, i1] * fu
    bottom = _lattice[j1, i0] * (1 - fu) + _lattice[j1, i1] * fu
    return top * (1 - fv) + bottom * fv

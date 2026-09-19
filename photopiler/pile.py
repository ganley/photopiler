"""Composing photos into a randomly arranged pile."""

import math
import os
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from . import camera, table
from .effects import (
    add_border,
    age_photo,
    apply_tone,
    border_widths,
    bordered_size,
    largest_print_size,
    resolve_age,
    resolve_border,
    resolve_tone,
)
from .options import SCALE_FRACTION, Age, Border, PileOptions, Tone

MAX_SIDE = 4000  # hard cap on output size, in pixels
MAX_ROTATION = 25  # degrees either way
EDGE_FRACTION = 0.25  # at most this much of a photo's width may fall off the canvas
PLACEMENT_CANDIDATES = 10  # best-candidate sampling: higher spreads photos more evenly

# Shared by all requests. Pillow and numpy release the GIL for most of their
# work, so threads run the per-print work on all CPUs.
_pool = ThreadPoolExecutor(max_workers=os.cpu_count() or 2, thread_name_prefix="pile")

SHADOW_BLUR = 12
SHADOW_OFFSET = (6, 10)
SHADOW_OPACITY = 0.55


@dataclass
class Placement:
    index: int  # which photo; placements are listed bottom of the pile first
    # Where the center sits within the range the edge rule allows on each axis:
    # 0 = as far left/up as allowed, 1 = as far right/down.
    position: tuple[float, float]
    angle: float


def uncapped_side(sizes, scale: float) -> float:
    return math.sqrt(scale * sum(w * h for w, h in sizes))


def canvas_side(sizes, scale: float) -> int:
    """Side of the square canvas whose area is `scale` × the total area of `sizes`."""
    return max(1, min(MAX_SIDE, round(uncapped_side(sizes, scale))))


def rotated_extent(size, angle: float) -> tuple[float, float]:
    """Bounding-box size of a (w, h) rectangle rotated by `angle` degrees."""
    w, h = size
    c, s = abs(math.cos(math.radians(angle))), abs(math.sin(math.radians(angle)))
    return w * c + h * s, w * s + h * c


def center_range(canvas: int, extent: float) -> tuple[float, float]:
    """Allowed range for a photo's center along one axis.

    `extent` is the photo's rotated bounding-box size along that axis. If the
    canvas is too small for the rule, the photo is centered.
    """
    lo, hi = extent * EDGE_FRACTION, canvas - extent * EDGE_FRACTION
    if lo > hi:
        return canvas / 2, canvas / 2
    return lo, hi


def choose_center(rng, side, size, placed_centers) -> tuple[float, float]:
    """Pick a center within bounds, preferring spots far from photos already placed."""
    x_lo, x_hi = center_range(side, size[0])
    y_lo, y_hi = center_range(side, size[1])
    candidates = [
        (rng.uniform(x_lo, x_hi), rng.uniform(y_lo, y_hi)) for _ in range(PLACEMENT_CANDIDATES)
    ]
    if not placed_centers:
        return candidates[0]
    return max(candidates, key=lambda c: min(math.dist(c, p) for p in placed_centers))


def with_shadow(photo: Image.Image) -> tuple[Image.Image, int]:
    """Return the RGBA photo on a larger transparent layer with a soft drop shadow,
    plus the padding added on each side."""
    pad = SHADOW_BLUR * 3 + max(SHADOW_OFFSET)
    layer_size = (photo.width + 2 * pad, photo.height + 2 * pad)

    shadow_alpha = Image.new("L", layer_size, 0)
    alpha = photo.getchannel("A").point(lambda a: round(a * SHADOW_OPACITY))
    shadow_alpha.paste(alpha, (pad + SHADOW_OFFSET[0], pad + SHADOW_OFFSET[1]))
    shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))

    layer = Image.new("RGBA", layer_size, (0, 0, 0, 255))
    layer.putalpha(shadow_alpha)
    layer.alpha_composite(photo, (pad, pad))
    return layer, pad


@dataclass(frozen=True)
class PrintStyle:
    """The concrete effects for one print, with any "random" options resolved."""

    tone: Tone
    border: Border
    age: Age
    noise_seed: tuple[int, int]


def resolve_styles(photos, options: PileOptions) -> list[PrintStyle]:
    """Decide each print's effects.

    Each effect's random per-photo choices come from its own RNG stream, separate
    from the layout and from each other, so changing one option never re-rolls
    another option's random choices. Choices are made here, in order, so the
    slow pixel work can then run in parallel without changing the result.
    """
    border_rng = random.Random(f"border-{options.seed}")
    tone_rng = random.Random(f"tone-{options.seed}")
    age_rng = random.Random(f"age-{options.seed}")
    return [
        PrintStyle(
            tone=resolve_tone(options.tone, tone_rng),
            border=resolve_border(options.border, border_rng),
            age=resolve_age(options.age, age_rng),
            noise_seed=(options.seed & 0xFFFFFFFF, i),
        )
        for i in range(len(photos))
    ]


def make_print(photo: Image.Image, style: PrintStyle) -> Image.Image:
    """Apply one print's effects. Tone before border, so borders stay paper-white
    on monochrome prints; aging last, so borders yellow along with the photo."""
    photo = apply_tone(photo, style.tone)
    left, top, _, _ = border_widths(photo.size, style.border)
    photo_box = (left, top, left + photo.width, top + photo.height)
    photo = add_border(photo, style.border)
    return age_photo(photo, style.age, np.random.default_rng(style.noise_seed), photo_box)


def style_photos(photos, options: PileOptions) -> list[Image.Image]:
    """Turn each photo into a finished print."""
    return list(_pool.map(make_print, photos, resolve_styles(photos, options)))


def plan_layout(photos, seed: int) -> list[Placement]:
    """Choose stacking order, rotations and positions for the photos.

    The plan depends only on the photos and the seed, never on the options. It
    is worked out at the default scale for each photo's largest possible print,
    and positions are stored relative to the range each photo may occupy, so
    changing borders, effects or the canvas size keeps the same arrangement.
    """
    rng = random.Random(seed)
    sizes = [largest_print_size(p.size) for p in photos]
    side = uncapped_side(sizes, SCALE_FRACTION)
    order = list(range(len(photos)))
    rng.shuffle(order)
    layout, placed = [], []
    for i in order:
        angle = rng.uniform(-MAX_ROTATION, MAX_ROTATION)
        extent = rotated_extent(sizes[i], angle)
        center = choose_center(rng, side, extent, placed)
        placed.append(center)
        position = (
            _fraction_of_range(center[0], *center_range(side, extent[0])),
            _fraction_of_range(center[1], *center_range(side, extent[1])),
        )
        layout.append(Placement(i, position, angle))
    return layout


def render_pile(photos, options: PileOptions) -> Image.Image:
    if not photos:
        raise ValueError("need at least one photo")
    layout = plan_layout(photos, options.seed)
    styles = resolve_styles(photos, options)
    # Print sizes follow from the borders alone, so the canvas (and the table)
    # can be sized before any pixel work starts.
    print_sizes = [bordered_size(p.size, s.border) for p, s in zip(photos, styles)]
    side = canvas_side(print_sizes, options.scale)
    # If the size cap kicked in, shrink prints to keep their proportion of the canvas.
    # (Exactly 1 otherwise: rounding the side to whole pixels mustn't count.)
    uncapped = uncapped_side(print_sizes, options.scale)
    shrink = side / uncapped if uncapped > MAX_SIDE else 1.0

    # The slow work runs in parallel: the tabletop, and each print's effects,
    # rotation, shadow and projection. Only the pasting happens in pile order.
    canvas_future = _pool.submit(table.surface, side, options.tilt, shrink)

    def prepare(placement: Placement):
        photo = make_print(photos[placement.index], styles[placement.index])
        return place_print(photo, placement, side, shrink, options.tilt)

    layers = list(_pool.map(prepare, layout))
    canvas = canvas_future.result()
    for layer, position in filter(None, layers):
        canvas.paste(layer, position, layer)
    return camera.depth_of_field(canvas, options.tilt) if options.tilt > 0 else canvas


def place_print(photo: Image.Image, placement: Placement, side: int, shrink: float, tilt: float):
    """Rotate a print, add its shadow and work out where it goes.

    Returns (layer, position) ready to paste onto the canvas, or None if the
    print is out of view.
    """
    if shrink < 1:
        photo = photo.resize(
            (max(1, round(photo.width * shrink)), max(1, round(photo.height * shrink))),
            Image.Resampling.LANCZOS,
        )
    rotated = photo.convert("RGBA").rotate(
        placement.angle, resample=Image.Resampling.BICUBIC, expand=True
    )
    cx, cy = image_center(placement, rotated.size, side, tilt)
    layer, pad = with_shadow(rotated)
    if tilt <= 0:
        return layer, (round(cx - rotated.width / 2) - pad, round(cy - rotated.height / 2) - pad)
    # Lay the print on the table where the camera sees this spot, keeping its
    # real size, and project it into the image.
    tx, ty = camera.table_point(side, tilt, cx, cy)
    return camera.project(layer, (tx - layer.width / 2, ty - layer.height / 2), side, tilt)


def image_center(placement: Placement, size, side: int, tilt: float) -> tuple[float, float]:
    """Where in the output image a print's center goes.

    The edge rule applies to how big the print *looks* where it lands. Viewed
    overhead that is its actual size. With a tilted camera, prints look smaller
    toward the top of the image and bigger toward the bottom, so distant prints
    can go right up to the far edge and the pile fills the frame.
    """
    w, h = size
    if tilt <= 0:
        return (
            _point_in_range(placement.position[0], *center_range(side, w)),
            _point_in_range(placement.position[1], *center_range(side, h)),
        )
    y_lo = _settle(lambda y: EDGE_FRACTION * h * camera.magnification(side, tilt, y)[1], side * 0.5)
    y_hi = side - _settle(
        lambda y: EDGE_FRACTION * h * camera.magnification(side, tilt, side - y)[1], side * 0.5
    )
    cy = _point_in_range(placement.position[1], y_lo, y_hi) if y_lo <= y_hi else side / 2
    apparent_w = w * camera.magnification(side, tilt, cy)[0]
    cx = _point_in_range(placement.position[0], *center_range(side, apparent_w))
    return cx, cy


def _settle(f, start: float, steps: int = 20) -> float:
    """Solve y = f(y) by repeated substitution (f changes slowly, so this converges)."""
    y = start
    for _ in range(steps):
        y = f(y)
    return y


def _fraction_of_range(value: float, lo: float, hi: float) -> float:
    return 0.5 if hi <= lo else (value - lo) / (hi - lo)


def _point_in_range(fraction: float, lo: float, hi: float) -> float:
    return lo + fraction * (hi - lo)

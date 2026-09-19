"""Photographing the pile from an angle: perspective and depth of field.

The pile lies on a table. A pinhole camera, aimed at the center of the image,
tilts `tilt` degrees away from looking straight down, so the top of the image
sees farther across the table than the bottom.

The layout is worked out in image space, as for the overhead view, and each
photo's center is projected onto the part of the table the camera sees there.
Prints keep their real size on the table, so distant ones look smaller and
near ones bigger, and the pile fills the whole frame at any angle instead of
leaving empty table at the back.

Coordinates: output pixels (x, y) span [0, side]²; table coordinates are in
the same units, matching the output exactly along the center row.
"""

import math

import numpy as np
from PIL import Image, ImageFilter

# In multiples of the image side. A mild telephoto, as you'd use to shoot a desk
# at an angle from a little way back: far prints look about half the size of
# near ones at 60°, rather than a quarter with a normal lens.
FOCAL_LENGTH = 2.5

# Blur radius at the top and bottom edges of the image, as a fraction of the
# image side, scaled by sin(tilt): about 0.4% of the side at 45°. It is zero at
# the center row, where the camera is focused.
DEPTH_OF_FIELD_BLUR = 0.006


def _params(side: int, tilt: float):
    """Half the side, cos(tilt), the perspective strength, and the zoom.

    The camera zooms in by 1/sqrt(cos(tilt)) so prints cover about the same
    share of the frame as overhead: foreshortening squashes them vertically by
    cos(tilt), and the zoom spreads that over both directions.
    """
    t = math.radians(tilt)
    cos_t = math.cos(t)
    return side / 2, cos_t, math.tan(t) / (FOCAL_LENGTH * side), 1 / math.sqrt(cos_t)


def table_point(side: int, tilt: float, x: float, y: float) -> tuple[float, float]:
    """Where on the table the camera sees output pixel (x, y)."""
    half, cos_t, k, zoom = _params(side, tilt)
    xc, yc = x - half, y - half
    d = 1 + k * yc  # proportional to 1 / distance from the camera
    return half + xc / (zoom * d), half + yc / (zoom * cos_t * d)


def magnification(side: int, tilt: float, y: float) -> tuple[float, float]:
    """How much bigger (horizontally, vertically) something on the table looks
    at output row y than it would overhead. Both are 1 overhead; with a tilt,
    things shrink toward the top of the image and vertically foreshorten."""
    half, cos_t, k, zoom = _params(side, tilt)
    d = 1 + k * (y - half)
    return zoom * d, zoom * cos_t * d * d


def image_point(side: int, tilt: float, tx: float, ty: float):
    """Where table point (tx, ty) appears in the output, or None if it is
    behind the camera. The inverse of `table_point`."""
    half, cos_t, k, zoom = _params(side, tilt)
    u = (ty - half) * zoom * cos_t
    if 1 - k * u <= 1e-6:
        return None
    yc = u / (1 - k * u)
    return half + (tx - half) * zoom * (1 + k * yc), half + yc


def project(layer: Image.Image, top_left: tuple[float, float], side: int, tilt: float):
    """Project an RGBA layer lying on the table (its top-left corner at table
    point `top_left`) into the output image.

    Returns (image, position) ready to paste into the side × side output, or
    None if the layer is out of view.
    """
    x0, y0 = top_left
    w, h = layer.size
    corners = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    projected = [image_point(side, tilt, x, y) for x, y in corners]
    if any(p is None for p in projected):
        return None
    left = max(0, math.floor(min(p[0] for p in projected)))
    top = max(0, math.floor(min(p[1] for p in projected)))
    right = min(side, math.ceil(max(p[0] for p in projected)))
    bottom = min(side, math.ceil(max(p[1] for p in projected)))
    if right <= left or bottom <= top:
        return None
    box_w, box_h = right - left, bottom - top

    # Shrink a distant layer first, so the perspective resampling doesn't alias.
    full_w = max(p[0] for p in projected) - min(p[0] for p in projected)
    full_h = max(p[1] for p in projected) - min(p[1] for p in projected)
    scale = min(1.0, max(full_w / w, full_h / h))
    if scale < 0.9:
        layer = layer.resize(
            (max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS
        )
        scale_x, scale_y = layer.width / w, layer.height / h
    else:
        scale_x = scale_y = 1.0

    box = [(0, 0), (box_w, 0), (box_w, box_h), (0, box_h)]
    sources = []
    for bx, by in box:
        tx, ty = table_point(side, tilt, left + bx, top + by)
        sources.append(((tx - x0) * scale_x, (ty - y0) * scale_y))
    coeffs = perspective_coefficients(box, sources)
    image = layer.transform((box_w, box_h), Image.Transform.PERSPECTIVE, coeffs,
                            Image.Resampling.BICUBIC)
    return image, (left, top)


def perspective_coefficients(out_points, in_points) -> list[float]:
    """The 8 coefficients Pillow's PERSPECTIVE transform needs to map each
    output point to its input point."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(out_points, in_points):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs += [u, v]
    return np.linalg.solve(np.array(rows, float), np.array(rhs, float)).tolist()


def depth_of_field(image: Image.Image, tilt: float) -> Image.Image:
    """Blur that grows with distance from the center row, where the camera focuses.

    For a tilted plane the blur is proportional to the distance from the focus
    row, so blending toward one blurred copy with a linear ramp approximates it.
    """
    side = image.height
    radius = DEPTH_OF_FIELD_BLUR * side * math.sin(math.radians(tilt))
    if radius < 0.5:
        return image
    blurred = image.filter(ImageFilter.GaussianBlur(radius))
    ramp = np.abs(np.linspace(-1, 1, side, dtype=np.float32))
    mask = Image.fromarray((ramp * 255).astype(np.uint8)[:, None], "L").resize(image.size)
    return Image.composite(blurred, image, mask)

import math

import numpy as np
import pytest
from PIL import Image

from photopiler import camera, pile
from photopiler.options import MAX_TILT, Border, PileOptions, clamp_tilt

SIDE = 1000
TILTS = [10, 30, 50, MAX_TILT]


def test_overhead_camera_is_the_identity():
    for x, y in [(0, 0), (SIDE, 0), (123, 456), (SIDE, SIDE)]:
        assert camera.table_point(SIDE, 0, x, y) == pytest.approx((x, y))
        assert camera.image_point(SIDE, 0, x, y) == pytest.approx((x, y))
    assert camera.magnification(SIDE, 0, 300) == pytest.approx((1, 1))


@pytest.mark.parametrize("tilt", TILTS)
def test_center_stays_put(tilt):
    assert camera.table_point(SIDE, tilt, SIDE / 2, SIDE / 2) == pytest.approx((SIDE / 2, SIDE / 2))


@pytest.mark.parametrize("tilt", TILTS)
def test_image_point_inverts_table_point(tilt):
    for x, y in [(0, 0), (SIDE, 0), (250, 800), (SIDE, SIDE)]:
        tx, ty = camera.table_point(SIDE, tilt, x, y)
        assert camera.image_point(SIDE, tilt, tx, ty) == pytest.approx((x, y))


@pytest.mark.parametrize("tilt", TILTS)
def test_far_side_recedes(tilt):
    """Things near the top of the image look smaller than near the bottom."""
    far_w, far_h = camera.magnification(SIDE, tilt, 0)
    near_w, near_h = camera.magnification(SIDE, tilt, SIDE)
    assert far_w < near_w and far_h < near_h
    top_left, top_right = (camera.table_point(SIDE, tilt, x, 0) for x in (0, SIDE))
    assert top_right[0] - top_left[0] > SIDE


@pytest.mark.parametrize("tilt", TILTS)
def test_prints_cover_the_same_area_at_the_center_row(tilt):
    """The zoom offsets foreshortening, so apparent area is unchanged there."""
    w, h = camera.magnification(SIDE, tilt, SIDE / 2)
    assert w * h == pytest.approx(1)


@pytest.mark.parametrize("tilt", TILTS)
def test_magnification_matches_the_projection(tilt):
    """Check the closed-form magnification against projecting a tiny square."""
    for y in (100, SIDE / 2, 900):
        tx, ty = camera.table_point(SIDE, tilt, SIDE / 2, y)
        eps = 0.01
        x1, y1 = camera.image_point(SIDE, tilt, tx + eps, ty + eps)
        assert ((x1 - SIDE / 2) / eps, (y1 - y) / eps) == pytest.approx(
            camera.magnification(SIDE, tilt, y), rel=1e-3
        )


@pytest.mark.parametrize("tilt", [15, MAX_TILT])
def test_perspective_coefficients_match_the_camera_model(tilt):
    corners = [(0, 0), (SIDE, 0), (SIDE, SIDE), (0, SIDE)]
    coeffs = camera.perspective_coefficients(
        corners, [camera.table_point(SIDE, tilt, x, y) for x, y in corners]
    )
    a, b, c, d, e, f, g, h = coeffs
    for x, y in [(250, 250), (700, 100), (SIDE / 2, 900)]:
        w = g * x + h * y + 1
        assert ((a * x + b * y + c) / w, (d * x + e * y + f) / w) == pytest.approx(
            camera.table_point(SIDE, tilt, x, y), abs=1e-6
        )


@pytest.mark.parametrize("y", [150, 500, 850])
def test_project_puts_a_layer_where_the_camera_sees_it(y):
    tilt = 45
    layer = Image.new("RGBA", (100, 60), (255, 0, 0, 255))
    tx, ty = camera.table_point(SIDE, tilt, 500, y)
    image, (left, top) = camera.project(layer, (tx - 50, ty - 30), SIDE, tilt)
    alpha = np.asarray(image.getchannel("A")) > 128
    rows, cols = np.nonzero(alpha)
    center = (left + cols.mean(), top + rows.mean())
    assert center == pytest.approx((500, y), abs=3)
    # Its apparent size follows the magnification at that row.
    mag_w, mag_h = camera.magnification(SIDE, tilt, y)
    assert np.ptp(cols) + 1 == pytest.approx(100 * mag_w, rel=0.1)
    assert np.ptp(rows) + 1 == pytest.approx(60 * mag_h, rel=0.15)


def test_project_skips_layers_out_of_view():
    layer = Image.new("RGBA", (50, 50), (255, 0, 0, 255))
    assert camera.project(layer, (-5000, 400), SIDE, 30) is None


def test_depth_of_field_keeps_the_center_sharp_and_blurs_the_edges():
    stripes = np.zeros((400, 400, 3), np.uint8)
    stripes[:, ::4] = 255
    img = Image.fromarray(stripes)
    out = np.asarray(camera.depth_of_field(img, MAX_TILT)).astype(float)
    assert out[200].std() == pytest.approx(stripes[200].astype(float).std(), rel=0.05)
    assert out[0].std() < stripes[0].std() * 0.7


PHOTO_COLOR = (40, 90, 220)  # blue: nothing like the wood


def longest_empty_band(image) -> float:
    """Height of the tallest run of rows with (almost) no photo in them, as a
    fraction of the image height. The test photos are solid blue."""
    pixels = np.asarray(image).astype(int)
    photo_per_row = (np.abs(pixels - np.array(PHOTO_COLOR)).max(axis=-1) <= 30).mean(axis=1)
    longest = run = 0
    for share in photo_per_row:
        run = run + 1 if share <= 0.1 else 0
        longest = max(longest, run)
    return longest / len(photo_per_row)


@pytest.mark.parametrize("seed", range(1, 6))
def test_tilted_pile_leaves_no_big_empty_band(seed):
    photos = [Image.new("RGB", (400, 300), PHOTO_COLOR) for _ in range(7)]
    flat = pile.render_pile(photos, PileOptions(seed=seed, border=Border.NONE))
    tilted = pile.render_pile(photos, PileOptions(seed=seed, border=Border.NONE, tilt=MAX_TILT))
    assert tilted.size == flat.size
    assert longest_empty_band(tilted) < 0.2


def test_clamp_tilt():
    assert clamp_tilt(None) == 0
    assert clamp_tilt(float("nan")) == 0
    assert clamp_tilt(-10) == 0
    assert clamp_tilt(90) == MAX_TILT
    assert clamp_tilt(math.pi) == math.pi


def test_web_accepts_tilt():
    from photopiler.web import app

    client = app.test_client()
    for tilt in ("0", "30", "99", "abc"):
        assert client.get(f"/pile.jpg?seed=1&tilt={tilt}").status_code == 200
    page = client.get("/?seed=1&tilt=30").get_data(as_text=True)
    assert 'name="tilt"' in page and 'value="30"' in page and f'max="{MAX_TILT}"' in page

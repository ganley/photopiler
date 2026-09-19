import math
import random

import pytest
from PIL import Image

from photopiler import pile
from photopiler.loading import WORK_AREA, demo_photos, normalize_size
from photopiler.options import (
    MAX_SCALE,
    MIN_SCALE,
    SCALE_FRACTION,
    PileOptions,
    clamp_scale,
)


def solid(w, h, color=(200, 50, 50)):
    return Image.new("RGB", (w, h), color)


def test_canvas_side_is_sqrt_of_scaled_area():
    sizes = [(100, 200), (300, 100)]
    assert pile.canvas_side(sizes, 0.5) == round(math.sqrt(0.5 * (20_000 + 30_000)))


def test_canvas_side_is_capped():
    assert pile.canvas_side([(10_000, 10_000)], 1.0) == pile.MAX_SIDE


def test_rotated_extent():
    assert pile.rotated_extent((100, 50), 0) == pytest.approx((100, 50))
    assert pile.rotated_extent((100, 50), 90) == pytest.approx((50, 100))
    w, h = pile.rotated_extent((100, 100), 45)
    assert w == pytest.approx(100 * math.sqrt(2))


def test_layout_covers_every_photo_once_with_fractional_positions():
    photos = [solid(120, 90) for _ in range(6)]
    layout = pile.plan_layout(photos, seed=4)
    assert sorted(p.index for p in layout) == list(range(6))
    for p in layout:
        assert 0 <= p.position[0] <= 1 and 0 <= p.position[1] <= 1
        assert abs(p.angle) <= pile.MAX_ROTATION


@pytest.mark.parametrize("scale", [MIN_SCALE, 0.35, SCALE_FRACTION, 0.8, MAX_SCALE])
def test_every_scale_keeps_photos_within_edge_rule(scale, monkeypatch):
    """Record where render_pile puts each photo and check the quarter-width rule."""
    pasted = []
    real_paste = Image.Image.paste

    def spy(self, im, box=None, mask=None):
        if self.size[0] == self.size[1] and im.mode == "RGBA":  # a layer onto the canvas
            pasted.append((self.size[0], im.size, box))
        return real_paste(self, im, box, mask)

    monkeypatch.setattr(Image.Image, "paste", spy)
    photos = [solid(400, 300) for _ in range(6)]
    pile.render_pile(photos, PileOptions(seed=5, scale=scale))

    assert len(pasted) == 6
    pad = pile.SHADOW_BLUR * 3 + max(pile.SHADOW_OFFSET)
    for side, (lw, lh), (x, y) in pasted:
        w, h = lw - 2 * pad, lh - 2 * pad  # the rotated photo inside the shadow layer
        cx, cy = x + pad + w / 2, y + pad + h / 2
        assert w / 4 - 1 <= cx <= side - w / 4 + 1
        assert h / 4 - 1 <= cy <= side - h / 4 + 1


def test_scale_changes_canvas_size():
    photos = [solid(400, 300) for _ in range(4)]
    small = pile.render_pile(photos, PileOptions(seed=1, scale=0.25))
    big = pile.render_pile(photos, PileOptions(seed=1, scale=1.0))
    assert big.width == pytest.approx(small.width * 2, abs=2)


def test_clamp_scale():
    assert clamp_scale(None) == SCALE_FRACTION
    assert clamp_scale(float("nan")) == SCALE_FRACTION
    assert clamp_scale(float("inf")) == SCALE_FRACTION
    assert clamp_scale(0.01) == MIN_SCALE
    assert clamp_scale(5) == MAX_SCALE
    assert clamp_scale(0.7) == 0.7


@pytest.mark.parametrize("seed", range(20))
def test_choose_center_respects_edge_rule(seed):
    rng = random.Random(seed)
    side, size = 1000, (400, 300)
    placed = []
    for _ in range(8):
        x, y = pile.choose_center(rng, side, size, placed)
        assert size[0] / 4 <= x <= side - size[0] / 4
        assert size[1] / 4 <= y <= side - size[1] / 4
        placed.append((x, y))


def test_center_range_falls_back_to_middle_when_canvas_too_small():
    assert pile.center_range(100, 1000) == (50, 50)


def test_normalize_size_hits_target_area():
    img = normalize_size(solid(4032, 3024))
    assert abs(img.width * img.height - WORK_AREA) / WORK_AREA < 0.01
    assert abs(img.width / img.height - 4032 / 3024) < 0.01


def test_same_seed_gives_same_pile():
    photos = [solid(120, 90, (i * 30, 100, 200)) for i in range(5)]
    a = pile.render_pile(photos, PileOptions(seed=7))
    b = pile.render_pile(photos, PileOptions(seed=7))
    c = pile.render_pile(photos, PileOptions(seed=8))
    assert a.tobytes() == b.tobytes()
    assert a.tobytes() != c.tobytes()


def test_parallel_render_matches_step_by_step():
    """Rendering prints in parallel must give exactly what doing it in order does."""
    from photopiler import camera, table
    from photopiler.options import Age, Border, Tone

    photos = [solid(160, 120, (i * 35, 90, 200 - i * 20)) for i in range(6)]
    for tilt in (0, 40):
        options = PileOptions(
            seed=11, border=Border.RANDOM, tone=Tone.RANDOM, age=Age.RANDOM, tilt=tilt
        )
        styles = pile.resolve_styles(photos, options)
        sizes = [p.size for p in (pile.make_print(ph, s) for ph, s in zip(photos, styles))]
        side = pile.canvas_side(sizes, options.scale)
        shrink = 1.0  # well under the size cap
        expected = table.surface(side, tilt, shrink)
        for placement in pile.plan_layout(photos, options.seed):
            printed = pile.make_print(photos[placement.index], styles[placement.index])
            placed = pile.place_print(printed, placement, side, shrink, tilt)
            if placed:
                expected.paste(placed[0], placed[1], placed[0])
        if tilt:
            expected = camera.depth_of_field(expected, tilt)
        assert pile.render_pile(photos, options).tobytes() == expected.tobytes()


def test_render_rejects_empty_input():
    with pytest.raises(ValueError):
        pile.render_pile([], PileOptions(seed=1))


def test_demo_photos_load_normalized():
    photos = demo_photos()
    assert len(photos) == 7
    for p in photos:
        assert p.mode == "RGB"
        assert abs(p.width * p.height - WORK_AREA) / WORK_AREA < 0.01


def test_web_routes():
    from photopiler.web import app

    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/healthz").get_data(as_text=True) == "ok"
    resp = client.get("/pile.jpg?seed=1")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"
    for scale in ("0.3", "9", "-1", "nan", "abc"):
        assert client.get(f"/pile.jpg?seed=1&scale={scale}").status_code == 200
    page = client.get("/?seed=1&scale=0.75").get_data(as_text=True)
    assert 'value="0.75"' in page

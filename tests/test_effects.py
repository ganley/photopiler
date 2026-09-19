import random
import re

import numpy as np
import pytest
from PIL import Image

from photopiler import effects, pile
from photopiler.options import Age, Border, PileOptions, Tone, parse_enum


def photo(w=400, h=300):
    return Image.new("RGB", (w, h), (200, 50, 50))


def test_no_border_adds_thin_dark_outline():
    out = effects.add_border(photo(), Border.NONE)
    w = effects.OUTLINE_WIDTH
    assert out.size == (400 + 2 * w, 300 + 2 * w)
    assert out.getpixel((0, 0)) == effects.OUTLINE_COLOR


def test_instamatic_border_is_even():
    out = effects.add_border(photo(), Border.INSTAMATIC)
    b = round(300 * effects.INSTAMATIC_BORDER)
    assert out.size == (400 + 2 * b, 300 + 2 * b)
    assert out.getpixel((b // 2, b // 2)) == effects.PAPER_COLOR


def test_polaroid_border_is_thicker_at_bottom():
    out = effects.add_border(photo(), Border.POLAROID)
    side = round(300 * effects.POLAROID_SIDE_BORDER)
    bottom = round(300 * effects.POLAROID_BOTTOM_BORDER)
    assert out.size == (400 + 2 * side, 300 + side + bottom)
    assert bottom > 2 * side
    assert out.getpixel((out.width // 2, out.height - bottom // 2)) == effects.PAPER_COLOR
    assert out.getpixel((out.width // 2, side + 5)) == (200, 50, 50)


def test_bordered_size_matches_rendered_print():
    for style in effects.CONCRETE_BORDERS:
        assert effects.bordered_size((400, 300), style) == effects.add_border(photo(), style).size


def test_largest_print_size_contains_every_style():
    big = effects.largest_print_size((400, 300))
    for style in effects.CONCRETE_BORDERS:
        w, h = effects.bordered_size((400, 300), style)
        assert w <= big[0] and h <= big[1]


def test_random_border_resolves_to_a_concrete_style():
    rng = random.Random(0)
    styles = {effects.resolve_border(Border.RANDOM, rng) for _ in range(50)}
    assert styles == set(effects.CONCRETE_BORDERS)


def test_fixed_border_is_not_randomized():
    assert effects.resolve_border(Border.POLAROID, random.Random(0)) is Border.POLAROID


def test_mono_has_no_color_but_stays_rgb():
    out = effects.apply_tone(photo(), Tone.MONO)
    assert out.mode == "RGB"
    r, g, b = out.getpixel((10, 10))
    assert r == g == b


def test_color_tone_leaves_photo_unchanged():
    img = photo()
    assert effects.apply_tone(img, Tone.COLOR) is img


def test_random_tone_resolves_to_both_tones():
    rng = random.Random(0)
    assert {effects.resolve_tone(Tone.RANDOM, rng) for _ in range(50)} == set(effects.CONCRETE_TONES)


def test_mono_print_keeps_paper_colored_border():
    prints = pile.style_photos([photo()], PileOptions(seed=1, border=Border.POLAROID, tone=Tone.MONO))
    assert prints[0].getpixel((1, 1)) == effects.PAPER_COLOR


def test_changing_tone_does_not_rechoose_random_borders():
    photos = [photo(40, 30) for _ in range(12)]
    sizes = [
        [p.size for p in pile.style_photos(photos, PileOptions(seed=9, tone=tone))]
        for tone in Tone
    ]
    assert sizes[0] == sizes[1] == sizes[2]


def gradient_photo():
    """A colorful photo with real variation, so aging has something to act on."""
    x = np.linspace(0, 255, 200, dtype=np.float32)
    rgb = np.stack(np.broadcast_arrays(x[None, :], x[:, None], 255 - x[None, :]), axis=-1)
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def saturation(img):
    return np.asarray(img.convert("HSV"), dtype=np.float32)[..., 1].mean()


def aged(level, img=None):
    return effects.age_photo(img or gradient_photo(), level, np.random.default_rng(0))


def test_no_aging_leaves_photo_unchanged():
    img = gradient_photo()
    assert effects.age_photo(img, Age.NONE, np.random.default_rng(0)) is img


def test_aging_lowers_saturation_progressively():
    levels = [Age.NONE, Age.LIGHT, Age.MEDIUM, Age.HEAVY]
    sats = [saturation(aged(level)) for level in levels]
    assert sats == sorted(sats, reverse=True)
    assert sats[-1] < sats[0] * 0.6


def test_aging_adds_more_grain_at_heavier_levels():
    flat = Image.new("RGB", (200, 200), (128, 128, 128))
    # Measure noise away from the edges, where the vignette changes brightness.
    stds = [np.asarray(aged(level, flat))[80:120, 80:120].std() for level in (Age.LIGHT, Age.HEAVY)]
    assert 0 < stds[0] < stds[1]


@pytest.mark.parametrize("border", effects.CONCRETE_BORDERS)
def test_grain_stays_off_the_border(border):
    flat = Image.new("RGB", (300, 200), (128, 128, 128))
    prints = pile.style_photos([flat], PileOptions(seed=2, border=border, age=Age.HEAVY))
    pixels = np.asarray(prints[0]).astype(np.int16)
    left, top, right, bottom = effects.border_widths(flat.size, border)
    # Along a border row, neighbors differ only through the smooth vignette.
    assert np.abs(np.diff(pixels[0], axis=0)).max() <= 2
    # Inside the photo there is visible grain.
    inner = pixels[top + 50 : top + 150, left + 100 : left + 200]
    assert inner.std() > 5


def test_aging_fades_blacks_and_whites():
    pixels = np.asarray(aged(Age.HEAVY, Image.new("RGB", (100, 100), (0, 0, 0))))[40:60, 40:60]
    assert pixels.mean() > 20  # blacks lifted
    pixels = np.asarray(aged(Age.HEAVY, Image.new("RGB", (100, 100), (255, 255, 255))))[40:60, 40:60]
    assert pixels.mean() < 245  # whites dulled


def test_aging_is_deterministic_for_a_seed():
    photos = [gradient_photo() for _ in range(3)]
    opts = PileOptions(seed=11, age=Age.RANDOM)
    a = [p.tobytes() for p in pile.style_photos(photos, opts)]
    b = [p.tobytes() for p in pile.style_photos(photos, opts)]
    assert a == b


def test_random_age_resolves_to_every_level():
    rng = random.Random(0)
    assert {effects.resolve_age(Age.RANDOM, rng) for _ in range(80)} == set(effects.CONCRETE_AGES)


def test_changing_age_does_not_rechoose_random_borders():
    photos = [photo(40, 30) for _ in range(12)]
    sizes = [
        [p.size for p in pile.style_photos(photos, PileOptions(seed=9, age=age))] for age in Age
    ]
    assert all(s == sizes[0] for s in sizes)


@pytest.mark.parametrize("border", list(Border))
@pytest.mark.parametrize("tone", list(Tone))
@pytest.mark.parametrize("age", list(Age))
def test_pile_renders_with_every_option(border, tone, age):
    photos = [photo(120, 90) for _ in range(4)]
    image = pile.render_pile(photos, PileOptions(seed=3, border=border, tone=tone, age=age))
    assert image.mode == "RGB"


def test_parse_enum_falls_back_on_bad_input():
    assert parse_enum(Border, "polaroid", Border.NONE) is Border.POLAROID
    assert parse_enum(Border, "bogus", Border.NONE) is Border.NONE
    assert parse_enum(Border, None, Border.NONE) is Border.NONE


def test_web_accepts_border_param():
    from photopiler.web import app

    client = app.test_client()
    page = client.get("/?seed=5&border=polaroid").get_data(as_text=True)
    assert re.search(r'name="border" value="polaroid"\s+checked', page)
    assert client.get("/pile.jpg?seed=5&border=instamatic").status_code == 200
    assert client.get("/pile.jpg?seed=5&border=bogus").status_code == 200
    assert client.get("/pile.jpg?seed=5&tone=mono").status_code == 200
    page = client.get("/?tone=random").get_data(as_text=True)
    assert re.search(r'name="tone" value="random"\s+checked', page)
    page = client.get("/?age=heavy").get_data(as_text=True)
    assert re.search(r'name="age" value="heavy"\s+checked', page)
    assert client.get("/pile.jpg?seed=5&age=random").status_code == 200

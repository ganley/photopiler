import numpy as np

from photopiler import table


def test_wood_colors_stay_within_the_palette():
    pixels = np.asarray(table.surface(300, 0)).reshape(-1, 3).astype(int)
    darkest = np.minimum(table.WOOD_LIGHT, table.WOOD_DARK)
    lightest = np.maximum(table.WOOD_LIGHT, table.WOOD_DARK)
    assert (pixels >= darkest - 1).all() and (pixels <= lightest + 1).all()


def test_wood_has_grain():
    pixels = np.asarray(table.surface(300, 0)).astype(float)
    # Grain runs along y, so colors vary much more across a row than down a column.
    across = pixels[150, :, 0].std()
    along = pixels[:, 150, 0].std()
    assert across > 3
    assert across > along


def test_surface_is_the_same_every_time_and_callers_get_their_own_copy():
    first = table.surface(200, 20)
    first.paste((255, 0, 0), (0, 0, 200, 200))  # a caller drawing on it
    second = table.surface(200, 20)
    assert second.getpixel((10, 10)) != (255, 0, 0)
    assert second.tobytes() == table.surface(200, 20).tobytes()


def test_tilt_changes_the_view_of_the_table():
    assert table.surface(200, 0).tobytes() != table.surface(200, 40).tobytes()


def test_wood_scale_follows_the_prints():
    """With prints shrunk to half size, the same wood appears at half size."""
    full = np.asarray(table.surface(400, 0, unit=1.0))
    half = np.asarray(table.surface(200, 0, unit=0.5)).astype(int)
    assert np.abs(full[::2, ::2].astype(int) - half).mean() < 12

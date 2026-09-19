# PhotoPiler

A small web app that turns a handful of photos into a picture of them lying in a
haphazard pile on a wooden desk, like a stack of old prints.

- **Borders:** Polaroid, Instamatic, none, or a random mix
- **Color:** color, monochrome, or a random mix
- **Aging:** none, light, medium, heavy, or random, which fades, warms and adds film grain
- **Canvas size:** from a crowded pile to a spread-out one
- **Camera angle:** from overhead down to 65°, with perspective and depth of field
- **Your own photos,** or the built-in demo set

Every pile comes from a random seed, so any result can be shared as a link and
reproduced exactly. Uploaded photos are processed in memory and never stored.

## Running locally

Requires Python 3.13 or newer.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/flask --app photopiler.web run --debug
```

Then open http://127.0.0.1:5000. Run the tests with `.venv/bin/pytest`.

## Layout

| Path | What it does |
| --- | --- |
| `photopiler/web.py` | Flask routes: the page, demo renders, uploads |
| `photopiler/pile.py` | Layout: where each print goes, rotations, shadows |
| `photopiler/effects.py` | Per-print effects: borders, monochrome, aging |
| `photopiler/camera.py` | Tilted-camera perspective and depth of field |
| `photopiler/table.py` | The procedural wooden tabletop |
| `photopiler/loading.py` | Loading and normalizing photos |
| `static/`, `templates/` | The page |
| `doc/` | The original spec and implementation plan |

A `Dockerfile` is included for deployment.

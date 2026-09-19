"""Flask web front end."""

import io
import random
from pathlib import Path

from flask import Flask, render_template, request, send_file
from PIL import Image, UnidentifiedImageError

from .loading import demo_photos, load_photo
from .options import (
    MAX_SCALE,
    MAX_TILT,
    MIN_SCALE,
    Age,
    Border,
    PileOptions,
    Tone,
    clamp_scale,
    clamp_tilt,
    parse_enum,
)
from .pile import render_pile

ROOT = Path(__file__).resolve().parent.parent

MAX_UPLOAD_FILES = 30

app = Flask(__name__, template_folder=ROOT / "templates", static_folder=ROOT / "static")
# The page shrinks photos before uploading (about 0.5 MB each), so this only
# stops unusually large requests from other clients.
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024

demo_photos()  # warm the cache at startup rather than on the first request

# The radio-button groups on the page: (PileOptions field / query param, legend, choices).
CHOICE_CONTROLS = [
    (
        "border",
        "Borders",
        {
            Border.POLAROID: "Polaroid",
            Border.INSTAMATIC: "Instamatic",
            Border.NONE: "None",
            Border.RANDOM: "Random",
        },
    ),
    (
        "tone",
        "Color",
        {
            Tone.COLOR: "Color",
            Tone.MONO: "Monochrome",
            Tone.RANDOM: "Random",
        },
    ),
    (
        "age",
        "Aging",
        {
            Age.NONE: "None",
            Age.LIGHT: "Light",
            Age.MEDIUM: "Medium",
            Age.HEAVY: "Heavy",
            Age.RANDOM: "Random",
        },
    ),
]


def _options_from_request() -> PileOptions:
    """Read options from the query string (GET) or form fields (POST)."""
    values = request.values
    seed = values.get("seed", type=int)
    if seed is None:
        seed = random.randrange(1_000_000)
    choices = {}
    for name, _, _ in CHOICE_CONTROLS:
        default = getattr(PileOptions, name)
        choices[name] = parse_enum(type(default), values.get(name), default)
    scale = clamp_scale(values.get("scale", type=float))
    tilt = clamp_tilt(values.get("tilt", type=float))
    return PileOptions(seed=seed, scale=scale, tilt=tilt, **choices)


def _jpeg_response(image):
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


def _error(message: str, status: int = 400):
    return message, status, {"Content-Type": "text/plain; charset=utf-8"}


def _query(options: PileOptions) -> dict:
    query = {"seed": options.seed, "scale": f"{options.scale:.2f}", "tilt": f"{options.tilt:g}"}
    for name, _, _ in CHOICE_CONTROLS:
        query[name] = getattr(options, name).value
    return query


@app.get("/")
def index():
    options = _options_from_request()
    return render_template(
        "index.html",
        options=options,
        query=_query(options),
        controls=CHOICE_CONTROLS,
        min_scale=MIN_SCALE,
        max_scale=MAX_SCALE,
        max_tilt=MAX_TILT,
        max_files=MAX_UPLOAD_FILES,
    )


@app.get("/pile.jpg")
def pile_jpg():
    """Render the demo photos."""
    return _jpeg_response(render_pile(demo_photos(), _options_from_request()))


@app.post("/pile")
def pile_upload():
    """Render uploaded photos (multipart field "photos"). Nothing is stored."""
    files = [f for f in request.files.getlist("photos") if f.filename]
    if not files:
        return _error("Please choose at least one photo.")
    if len(files) > MAX_UPLOAD_FILES:
        return _error(f"Please choose at most {MAX_UPLOAD_FILES} photos.")
    photos = []
    for f in files:
        try:
            photos.append(load_photo(f.stream))
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
            return _error(f"Couldn't read “{f.filename}” as a JPEG or PNG image.")
    return _jpeg_response(render_pile(photos, _options_from_request()))


@app.errorhandler(413)
def too_large(_):
    mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return _error(f"That's too much to upload at once (limit {mb} MB). Try fewer photos.", 413)

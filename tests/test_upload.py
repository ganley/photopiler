import io

import pytest
from PIL import Image

from photopiler import web
from photopiler.loading import load_photo


@pytest.fixture
def client():
    return web.app.test_client()


def encoded(fmt="JPEG", size=(300, 200), mode="RGB", color=(200, 60, 60), exif=None):
    buf = io.BytesIO()
    img = Image.new(mode, size, color)
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(buf, fmt, **kwargs)
    buf.seek(0)
    return buf


def post(client, files, **fields):
    data = {"seed": "1", **fields}
    data["photos"] = [(buf, name) for buf, name in files]
    return client.post("/pile", data=data, content_type="multipart/form-data")


def test_upload_renders_jpeg(client):
    resp = post(client, [(encoded(), "a.jpg"), (encoded("PNG"), "b.png")], border="polaroid")
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"
    assert Image.open(io.BytesIO(resp.data)).format == "JPEG"


def test_upload_is_deterministic_for_a_seed(client):
    first = post(client, [(encoded(), "a.jpg"), (encoded(), "b.jpg")], age="heavy").data
    second = post(client, [(encoded(), "a.jpg"), (encoded(), "b.jpg")], age="heavy").data
    assert first == second


def test_upload_accepts_transparent_png(client):
    png = encoded("PNG", mode="RGBA", color=(0, 0, 0, 0))
    assert post(client, [(png, "clear.png")]).status_code == 200


def test_exif_rotation_is_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90° clockwise to display
    photo = load_photo(encoded(size=(400, 200), exif=exif))
    assert photo.height > photo.width


def test_upload_rejects_non_image(client):
    resp = post(client, [(io.BytesIO(b"not an image"), "notes.txt")])
    assert resp.status_code == 400
    assert "notes.txt" in resp.get_data(as_text=True)


def test_upload_requires_a_photo(client):
    resp = client.post("/pile", data={"seed": "1"}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "at least one" in resp.get_data(as_text=True)


def test_upload_limits_file_count(client):
    files = [(encoded(size=(20, 20)), f"{i}.jpg") for i in range(web.MAX_UPLOAD_FILES + 1)]
    resp = post(client, files)
    assert resp.status_code == 400
    assert str(web.MAX_UPLOAD_FILES) in resp.get_data(as_text=True)


def test_upload_limits_request_size(client, monkeypatch):
    monkeypatch.setitem(web.app.config, "MAX_CONTENT_LENGTH", 1024 * 1024)
    big = io.BytesIO(b"\0" * (2 * 1024 * 1024))
    resp = post(client, [(big, "huge.jpg")])
    assert resp.status_code == 413
    assert "too much" in resp.get_data(as_text=True)


def test_page_offers_upload(client):
    page = client.get("/").get_data(as_text=True)
    assert 'id="upload"' in page and "app.js" in page

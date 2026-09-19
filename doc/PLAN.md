# PhotoPiler — Implementation Plan

## Context
[doc/SPEC.md](doc/SPEC.md) describes a public demo web app, written in Python, that turns a set of photos into one "haphazard pile of prints" image like [doc/example_photo_pile.png](doc/example_photo_pile.png). The spec asks for a usable MVP (demo photos, random placement and rotation) as quickly as possible, then six features added one at a time: borders, color/mono, aging, the canvas-size multiplier, and uploads. The app does not need to scale.

What's in the repo now:
- `demo_inputs/`: 7 iPhone JPEGs. Six are about 12 MP (4032×3024, 2–5 MB each). One is a small 1125×1252 screenshot. Several have **EXIF orientation tags**, and `IMG_4937` is tagged `upper-right`, which means it is mirrored.
- `scratch/old.py`: an OpenCV prototype for the aging effect (sepia matrix plus Gaussian noise). It's useful as a reference for the aging parameters.
- `venv/`: this was **copied from `../anthropic/venv`**, so `pip` and its shebangs point at the wrong path and don't work. It only has numpy and opencv installed. Recreate it; don't reuse it.
- It is not a git repo yet.

## Recommended stack
- **Flask** with server-rendered HTML (one Jinja template, a plain `<form>`, and a little vanilla JS). There's no SPA or build step. This is the fastest way to a working MVP.
- **Pillow + numpy** for all image work. I'd drop OpenCV. Pillow handles EXIF transposition (`ImageOps.exif_transpose`), rotation with an alpha channel (`rotate(expand=True)` on RGBA), alpha compositing, and blur for shadows. It's also a much smaller dependency to deploy than `opencv-python`, which would need `-headless` on servers.
- **gunicorn** to serve it in production. **pytest** for tests.
- Keep rendering **stateless**. Every render is a pure function of (images, options, seed), so nothing needs to be stored on the server.

## Code layout
```
photopiler/
  __init__.py
  options.py    # dataclass PileOptions + enums: Border{NONE,INSTAMATIC,POLAROID,RANDOM},
                #   Tone{COLOR,MONO,RANDOM}, Age{NONE,LIGHT,MEDIUM,HEAVY,RANDOM}; SCALE_FRACTION default
  loading.py    # open → exif_transpose → convert RGB → downscale to working size; demo-image cache
  effects.py    # add_border(), to_mono(), age_photo(level)
  pile.py       # canvas sizing, placement, rotation, shadow, compositing → PIL.Image
  web.py        # Flask app: GET / (form), GET /pile.jpg?…&seed= (demo render), POST /pile (uploads)
templates/index.html
static/ (tiny CSS/JS, optional table-texture background)
tests/
requirements.txt, Dockerfile (or render.yaml), README.md
```
For each photo, the processing runs in this order: **load → normalize size → color/mono → border → age → to RGBA → rotate → shadow → paste**. Aging happens after the border so that white borders also yellow and pick up grain, which looks more authentic.

## Phases
The time estimates are for focused work. Aesthetic tuning is the thing most likely to run long; see Risks.

**Workflow:** Implement one phase, then stop and hand over for local testing (`flask --app photopiler.web run`). Start the next phase only after the user approves. All testing is local until Phase 6 is done, and then we deploy (Phase 7). The open questions below are settled with their defaults.

### Phase 0 — Scaffold (about 1–2 h)
- Copy this plan to `doc/PLAN.md`.
- Run `git init` and add a `.gitignore` for venv, `.DS_Store`, and `scratch/output.jpg`. Create a fresh venv and add `requirements.txt`.
- Add a `Dockerfile` early, pinned to Python 3.13. To mimic a free-tier host without deploying, run it locally with `docker run --memory=512m` (optional; needs Docker Desktop).

### Phase 1 — MVP pile from demo inputs (about 0.5–1 day)
- `loading.py`: apply `exif_transpose`, then **normalize every photo to roughly the same working area** (for example, about 1 MP, or a longest edge of about 1200 px). Without this step the 1125×1252 screenshot would come out tiny next to the 12 MP photos. Cache the processed demo images in memory at startup.
- Canvas sizing: `canvas_area = SCALE_FRACTION × Σ(photo areas)`, where the areas are the normalized ones. Start with `SCALE_FRACTION = 0.5`. A value below 1 is what produces the overlap. Make the canvas square, like the example, with `side = sqrt(canvas_area)`. Also apply a **hard cap on output pixels**, for example a 4000 px longest side.
- Placement: give each photo a random angle in about ±25°. Place it so that its rotated bounding box never extends off the canvas by more than ¼ of its width: the center x must be in `[w/4, W − w/4]` using the rotated bounding-box width, and the same for y. This is the "quarter of their width" rule from the spec.
  - Pure uniform random placement leaves gaps and clusters. Use **best-candidate sampling** instead: generate about 10 random candidates and keep the one farthest from the photos already placed. Tuning `SCALE_FRACTION` then decides whether the background shows through.
- Compositing: use a dark or neutral background, and give each photo a **soft drop shadow** (the alpha mask blurred with `GaussianBlur` and offset). The shadow is cheap and is most of what makes it read as a real pile.
- Web: the `/` page shows the image with a "Shuffle" button. `GET /pile.jpg?seed=N` returns a JPEG. The seed makes any output reproducible and linkable.
- Tests: check that the canvas size formula is correct, that placements stay within bounds, and that the same seed gives identical output.

### Phase 2 — Borders, then user control (about 0.5 day)
- `add_border(img, style)`:
  - Instamatic: a uniform off-white border of about 5% of the short side.
  - Polaroid: about 6% on the sides and top, and about 22% at the bottom. Don't crop to square; see the open questions.
- Add a `border` radio group (none, instamatic, polaroid, random) as a query parameter. Random is chosen per photo using the seeded RNG.

### Phase 3 — Color vs. monochrome, then user control (about 2 h)
- `to_mono`: `ImageOps.grayscale`, converted back to RGB. Mono needs to be done before the border so the border stays white.
- Add a `tone` control: color, mono, or random.

### Phase 4 — Aging effect, then user control (about 1 day, mostly tuning)
- `age_photo(img, level)` takes a parameter table keyed by level. Each level sets: saturation factor (`ImageEnhance.Color`), contrast fade (a lifted black point), warm/sepia tint strength (blended from the matrix in `scratch/old.py`), Gaussian noise sigma, and, optionally, a vignette.
  - Approximate values: light = 0.8 saturation, noise σ 6. Medium = 0.55, σ 12. Heavy = 0.3, σ 20, plus a stronger tint.
- Scale noise to the working resolution, not the source resolution.
- Add an `age` control: none, light, medium, heavy, or random.

### Phase 5 — Size multiplier control (about 1 h)
- Add a slider for `scale` (for example 0.25–1.0), clamped on the server. The output-pixel cap still applies.

### Phase 6 — User uploads (about 1 day)
- Add `<input type="file" multiple accept="image/jpeg,image/png">`. **Downscale on the client** to about a 1600 px longest edge using canvas and `toBlob` before uploading. This keeps each request to about 2 MB even for 12 MP phone photos, and it avoids host limits on request size and memory.
- `POST /pile` takes the multipart files plus the options and returns the JPEG. The page JS shows it and offers a download link.
- To reshuffle without uploading again, keep the downscaled blobs in browser memory and re-POST them. The server keeps nothing, which also avoids privacy questions.
- Server-side limits: at most about 30 files, `MAX_CONTENT_LENGTH` of about 40 MB, `Image.MAX_IMAGE_PIXELS`, and reject files Pillow can't open. Return a friendly error for 0 images.

### Phase 7 — Deploy (done)
- The code is on GitHub at https://github.com/ganley/photopiler (public). The reference image `doc/example_photo_pile.png` is kept out of the repo because its source is unknown.
- The app is deployed on Fly.io at https://photopiler.fly.dev/ as the app `photopiler` in region `iad`, on one `shared-cpu-2x` machine with 1 GB. It stops when idle and starts on demand. The configuration is in `fly.toml`; deploy with `fly deploy --ha=false`.
- Measured on Fly after the speedups:
  - Demo shuffle: about 0.9–1.0 s.
  - Heavy aging: about 1.3 s.
  - Tilted view: about 2.3 s.
  - Worst case (maximum canvas size, 65°, heavy aging): about 5 s.
  - Cold start after idle: about 3.7 s for the page, then about 3 s for the first pile.
  - Peak memory: about 330 MB of 1 GB.
- The speedups were: per-print work in parallel on a thread pool; the wooden table cached in 256 px size steps, with the common ones generated at startup; and a fix for a rounding bug that resized every print on every render.
- The machine is now **always on** (`auto_stop_machines = "off"`, `min_machines_running = 1`), so there are no cold starts. It costs about $6.64/month.

## Areas of high uncertainty that could threaten the schedule
1. **Aesthetic quality and tuning (highest risk).** "Looks like a pile" and "looks old" are subjective. Placement, shadow, border proportions, and aging parameters can each absorb unlimited iteration. *Mitigation:* agree up front on a "good enough" bar per phase, keep all tunables as named constants in one place, and add a `/debug` page that renders the same seed at several settings side by side for fast comparison.
2. **Memory and CPU on a cheap host.** The sum of areas for the demo set is about 75 MP. Rendering at source resolution with fraction 0.5 would mean a ~37 MP RGBA canvas (~150 MB) plus rotated copies, which will fail on a 512 MB free tier and take many seconds. *Mitigation:* normalize inputs before sizing (Phase 1), cap output pixels, downscale uploads on the client, and optionally run the local Docker container capped at 512 MB so memory problems show up before deployment.
3. **Spec ambiguity in canvas sizing.** "Sum of areas × fraction" depends heavily on input resolution. A phone photo and a screenshot give very different canvases. The plan interprets it as normalized areas with a pixel cap. The canvas aspect ratio isn't specified; the plan uses square. Confirm both.
4. **Upload edge cases (Phase 6).** iPhones often share **HEIC** files, which the spec excludes but users will try. There are also EXIF rotation and mirroring, huge panoramas, PNGs with transparency, CMYK JPEGs, and request-size limits (Cloud Run's is 32 MB, for example). *Mitigation:* client-side downscaling turns most of these into a clean JPEG. Add `pillow-heif` later only if needed.
5. **Cold starts and timeouts on free hosting.** A free tier that sleeps can take 30–60 s to wake up, which looks broken in a live demo. *Mitigation:* use a paid tier (~$5–7/mo) for demo days, or ping the app beforehand.
6. **Python 3.14 toolchain.** The local interpreter is 3.14. Some hosts' default images lag behind. *Mitigation:* pin 3.12 or 3.13 in the Dockerfile or runtime config, and test locally under the same version.

Lower-risk items: borders, mono, the size slider, and the Flask plumbing are all well understood.

## Hosting advice
*Revised after Phase 6. The user is fine paying a little for more flexibility or better performance.*

**Memory measurements** (as of the camera-angle feature): the app uses about 110 MB at idle once the demo photos are loaded. A worst-case render (canvas size at maximum, heavy aging, 45° tilt) adds about 250 MB, and takes about 1.6 s on a laptop. Two renders at once would overflow a 512 MB instance, so plan for about **1 GB**.

My recommendation is **Fly.io**, deploying the existing Dockerfile, with 1 GB RAM and 1–2 shared CPUs.
- It costs roughly $5–10/month running continuously. It can stop itself when idle and start again on the next request in about 1–2 s, which brings demo costs close to zero.
- Resizing memory or CPU is one command, and it gives HTTPS and a `*.fly.dev` URL.
- Start command: `gunicorn -w 1 --threads 4 -t 60 photopiler.web:app`. One worker process with threads, rather than several worker processes, avoids keeping a separate copy of the demo photos in memory for each.

Alternatives:
- **Railway (Hobby, about $5/mo plus usage)**: deploys from a GitHub push through a web UI, and memory scales automatically. It's the easiest option, at a similar cost.
- **Render Standard (~$25/mo, 2 GB)**: the simplest setup. The $7 Starter plan's 512 MB is now too tight.
- **Google Cloud Run**: close to free at demo traffic, with 2 GB instances and a cold start of a few seconds. It takes more setup: a GCP account and gcloud.
- **Hugging Face Spaces**: free with lots of RAM, but the URL and branding are less conventional.

**Performance option:** a single render mostly uses one CPU core. With 2 CPUs, the per-photo styling could run in parallel threads (Pillow and numpy can use several cores from threads), which would roughly halve render time.

Prices change often; check them before committing. The Dockerfile makes it quick to move between hosts.

## Decisions (confirmed by the user)
- Canvas aspect ratio: **square** (like the example). Alternatives are 4:3 or matching the average photo aspect.
- Polaroid style: **keep the photo's aspect ratio** rather than cropping to square like a real Polaroid.
- Background: **plain kraft-brown tabletop** (changed from dark after Phase 6).
- Hosting budget: **a modest monthly cost is fine** if it buys flexibility or performance (updated after Phase 6).
- Hosting is deferred until after some further UI and feature changes.

## Verification
- `pytest`: unit tests for the sizing formula, placement bounds, seeded determinism, border dimensions, each age level changing the pixel statistics as expected (lower saturation, higher variance), and the upload endpoint (valid images, a non-image file, zero files, an oversized request).
- Manual: run `flask --app photopiler.web run`, then check the demo render and every option combination against the example image. Check that `IMG_4937` isn't mirrored or rotated. Upload a mix of JPG and PNG from a phone.
- After each phase: the user tests locally before the next phase starts. After Phase 7: load the public URL from another network or device and time a render (target under 3 s when warm).

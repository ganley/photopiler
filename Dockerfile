FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY photopiler/ photopiler/
COPY templates/ templates/
COPY static/ static/
COPY demo_inputs/ demo_inputs/

ENV PORT=8000
# One worker process with a couple of threads: renders are memory-hungry
# (about 250 MB at worst), and a single process keeps one copy of the demo
# photos and the cached tabletops. Pillow and numpy release the GIL for most
# of their work, so threads still use both CPUs.
CMD exec gunicorn --workers 1 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT photopiler.web:app

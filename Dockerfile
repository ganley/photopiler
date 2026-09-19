FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY photopiler/ photopiler/
COPY templates/ templates/
COPY static/ static/
COPY demo_inputs/ demo_inputs/

ENV PORT=8000
CMD gunicorn -w 2 -t 60 -b 0.0.0.0:$PORT photopiler.web:app

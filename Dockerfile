# BioManager web app for a lab server. Built and run by deploy/compose.yaml;
# see deploy/README.md. The compiled CSS/JS are committed, so no Node here.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Time-zone data, so TZ (the lab's zone, from deploy/.env) sets the app's
# "today" and the times it shows; slim images leave it out.
RUN apt-get update -q && apt-get install -y -q --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# pywebview is for the desktop app only and needs GUI libraries.
COPY requirements.txt .
RUN grep -v pywebview requirements.txt > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

COPY app app
COPY migrations migrations
COPY scripts scripts
COPY alembic.ini wsgi.py gunicorn.conf.py ./

# The release this image is (the release workflow passes it), for What's new
# and the anonymous counts; a build from source leaves it out ("server").
ARG BIOMANAGER_VERSION=""
RUN if [ -n "$BIOMANAGER_VERSION" ]; then echo "$BIOMANAGER_VERSION" > VERSION; fi

# Everything the app writes lives on /data: the signing key, the setup code
# and uploads. The code itself is read-only to the app's user. /labkey is
# where it writes the lab's key for the backup service (deploy/compose.yaml):
# a named volume mounted there takes its owner from this folder.
RUN useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin biomanager \
 && mkdir -p /data/uploads /labkey && chown -R biomanager:biomanager /data /labkey
USER biomanager

ENV BIOMANAGER_DATA_DIR=/data \
    BIOMANAGER_UPLOADS_DIR=/data/uploads \
    BIOMANAGER_BIND=0.0.0.0:8000 \
    BIOMANAGER_PROXY_HOPS=1
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]

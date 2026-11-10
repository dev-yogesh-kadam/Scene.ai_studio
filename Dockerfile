# Scene.ai in one image: the web studio and admin console (apps/web) and the phone site (apps/mobile) built with Node,
# HyperFrames (motion graphics) with the Chrome it renders in, then served by the Python backend from a slim image.
# Every setting comes from SCENE_* environment variables (docs/azure.md); nothing is read from a config.json inside the
# image.
#
#   docker build -t scene-ai .
#   docker compose up            (docker-compose.yml: with PostgreSQL, Azurite and Redis, for local use)

# ---------------------------------------------------------------- 1. the client apps
FROM node:24.11-bookworm-slim AS web
WORKDIR /src
# The workspaces' package files first, so `npm ci` is cached until a dependency changes.
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY apps/mobile/package.json apps/mobile/
COPY packages/shared/package.json packages/shared/
RUN npm ci --no-audit --no-fund
COPY apps apps
COPY packages packages
RUN npm run build -w apps/web && npm run build -w apps/mobile

# ---------------------------------------------------------------- 2. HyperFrames and its Chrome (motion graphics)
# motion/'s packages as its lock pins them, and the chrome-headless-shell HyperFrames renders in, fetched here once so
# no render waits for (or fails on) a download. /opt/hyperframes/chrome-headless-shell names it, whatever its version.
FROM node:24.11-bookworm-slim AS motion
WORKDIR /app/motion
COPY motion/package.json motion/package-lock.json ./
# ffprobe-static carries ffprobe for every system (about 300 MB): only Linux x64's is kept, the one motion.py uses here.
RUN npm ci --no-audit --no-fund \
 && find node_modules/ffprobe-static/bin -mindepth 1 -maxdepth 1 ! -name linux -exec rm -rf {} + \
 && find node_modules/ffprobe-static/bin/linux -mindepth 1 -maxdepth 1 ! -name x64 -exec rm -rf {} + \
 && test -x node_modules/ffprobe-static/bin/linux/x64/ffprobe
ENV HYPERFRAMES_CACHE_DIR=/opt/hyperframes HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1
RUN node node_modules/hyperframes/bin/hyperframes.mjs browser ensure \
 && ln -s "$(find /opt/hyperframes -type f -name chrome-headless-shell | head -n 1)" /opt/hyperframes/chrome-headless-shell \
 && test -x /opt/hyperframes/chrome-headless-shell
COPY motion/templates templates

# ---------------------------------------------------------------- 3. the backend
FROM python:3.14-slim-bookworm AS app
# pg_dump and pg_restore of the server's major version (backups, the weekly restore test), from PostgreSQL's own
# repository: Debian's are older than 18 and refuse a newer server. Then what Node.js and Chrome need to run
# (HyperFrames), and fonts for the pages it renders.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get install -y --no-install-recommends libstdc++6 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
      libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
      libcairo2 libx11-6 libxcb1 libxext6 libdbus-1-3 libexpat1 libglib2.0-0 fonts-liberation fonts-dejavu-core \
 && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    SCENE_HOST=0.0.0.0 SCENE_PORT=8080 SCENE_CONSOLE_HOST=0.0.0.0 SCENE_CONSOLE_PORT=8090 \
    SCENE_STORAGE_DIR=/data/storage SCENE_BACKUP_DIR=/data/backups SCENE_LOG_FORMAT=json \
    SCENE_SECRET_KEY_FILE=/data/secret.key \
    HYPERFRAMES_BROWSER_PATH=/opt/hyperframes/chrome-headless-shell HYPERFRAMES_CACHE_DIR=/tmp/hyperframes
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY workflows workflows
COPY scripts/migrate.py scripts/move_media.py scripts/backfill_embeddings.py scripts/
COPY --from=web /src/apps/web/dist apps/web/dist
COPY --from=web /src/apps/mobile/dist apps/mobile/dist
COPY apps/web/public/fonts apps/web/public/fonts
COPY --from=motion /usr/local/bin/node /usr/local/bin/node
COPY --from=motion /app/motion motion
COPY --from=motion /opt/hyperframes /opt/hyperframes

# The app runs as an account of its own, never root; /data is its only writable place (a volume, or Azure Files), with
# the folder HyperFrames keeps the Google Fonts a page names in. The build stops here when Node.js or Chrome could not
# start (a library missing).
RUN useradd --create-home --uid 10001 scene && mkdir -p /data /app/motion/.fonts && chown scene /data /app/motion/.fonts \
 && node --version \
 && ! ldd /opt/hyperframes/chrome-headless-shell | grep "not found"
USER scene
EXPOSE 8080 8090
# /healthz: the process answers (liveness). /readyz: the database and the media storage answer (readiness).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c \
  "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('SCENE_PORT','8080'), timeout=4)"
WORKDIR /app/backend
CMD ["python", "-m", "scene"]

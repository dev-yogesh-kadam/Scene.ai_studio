# Scene.ai in one image: the web studio and admin console (apps/web) and the phone site (apps/mobile) built with Node,
# then served by the Python backend from a slim image. Every setting comes from SCENE_* environment variables
# (docs/azure.md); nothing is read from a config.json inside the image.
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

# ---------------------------------------------------------------- 2. the backend
FROM python:3.14-slim-bookworm AS app
# pg_dump and pg_restore of the server's major version (backups, the weekly restore test), from PostgreSQL's own
# repository: Debian's are older than 18 and refuse a newer server.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    SCENE_HOST=0.0.0.0 SCENE_PORT=8080 SCENE_CONSOLE_HOST=0.0.0.0 SCENE_CONSOLE_PORT=8090 \
    SCENE_STORAGE_DIR=/data/storage SCENE_BACKUP_DIR=/data/backups SCENE_LOG_FORMAT=json \
    SCENE_SECRET_KEY_FILE=/data/secret.key
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY workflows workflows
COPY scripts/migrate.py scripts/move_media.py scripts/backfill_embeddings.py scripts/
COPY --from=web /src/apps/web/dist apps/web/dist
COPY --from=web /src/apps/mobile/dist apps/mobile/dist

# The app runs as an account of its own, never root; /data is its only writable place (a volume, or Azure Files).
RUN useradd --create-home --uid 10001 scene && mkdir -p /data && chown scene /data
USER scene
EXPOSE 8080 8090
# /healthz: the process answers (liveness). /readyz: the database and the media storage answer (readiness).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c \
  "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('SCENE_PORT','8080'), timeout=4)"
WORKDIR /app/backend
CMD ["python", "-m", "scene"]

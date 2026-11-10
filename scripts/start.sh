#!/bin/sh
# Start Scene.ai on macOS or Linux. The first run creates a Python environment in .venv.
cd "$(dirname "$0")/.." || exit 1
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
[ -x .venv/bin/python ] || "$PY" -m venv .venv || exit 1
.venv/bin/python -m pip install -q --disable-pip-version-check -r backend/requirements.txt || exit 1
[ -f config.json ] || cp config.example.json config.json
# Motion graphics need Node.js. Without it the studio still runs; that section just says what is missing.
# npm ls fails when what is installed is not what package.json pins (a new HyperFrames): it is installed again then.
if command -v npm >/dev/null 2>&1 && ! (cd motion && npm ls --depth=0 >/dev/null 2>&1); then (cd motion && npm install --no-audit --no-fund); fi
# The phone site (/m/) is built from apps/mobile/ the first time; after a change to it, run "npm run build" there.
# Its packages, and the web studio's, are installed once at the root (npm workspaces: apps/*, packages/*).
if command -v npm >/dev/null 2>&1 && [ ! -f apps/mobile/dist/index.html ]; then
  { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build -w apps/mobile
fi
# The studio and the admin console (apps/web) are built when there is no build yet or their files changed after it.
if command -v npm >/dev/null 2>&1 && node apps/web/scripts/stale.mjs; then
  { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build -w apps/web
fi
cd backend && exec ../.venv/bin/python -m scene

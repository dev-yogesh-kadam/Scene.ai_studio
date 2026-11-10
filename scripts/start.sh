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
# HyperFrames renders in a Chrome of its own: fetched here the first time (about 150 MB), not in the middle of a user's
# first render. Once it is there this takes a moment and needs no network.
if command -v node >/dev/null 2>&1 && [ -f motion/node_modules/hyperframes/bin/hyperframes.mjs ]; then
  HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 node motion/node_modules/hyperframes/bin/hyperframes.mjs browser ensure >/dev/null 2>&1 \
    || echo "HyperFrames could not fetch its Chrome now: the first motion graphics render will."
fi
# The packages of the web studio and the phone site are installed once at the root (npm workspaces: apps/*,
# packages/*), and again when package-lock.json or a package.json changed (after a git pull).
if command -v npm >/dev/null 2>&1 && node scripts/start.stale.mjs packages; then npm install --no-audit --no-fund; fi
# The phone site (/m/, apps/mobile) and the studio with the admin console (apps/web) are built when there is no build
# yet or a file they are built from changed after it.
if command -v npm >/dev/null 2>&1 && node scripts/start.stale.mjs mobile; then npm run build -w apps/mobile; fi
if command -v npm >/dev/null 2>&1 && node apps/web/scripts/stale.mjs; then npm run build -w apps/web; fi
# Each line the studio prints reaches the terminal, or a file its output is sent to, at once.
export PYTHONUNBUFFERED=1
cd backend && exec ../.venv/bin/python -m scene

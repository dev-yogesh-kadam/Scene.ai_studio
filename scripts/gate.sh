#!/usr/bin/env bash
# The whole gate in one command (bash; scripts/gate.ps1 is the same for PowerShell): types, lint, design tokens, unit
# tests, pytest, the test order check, the agent's evals (replay), the web build with its bundle budget, Playwright,
# the smoke test, and (with --models) scripts/check_models.py, which calls Claude for real. One summary table at the end.
#
#   . testenv.sh scene_test_me; SCENE_TEST_PORT_BASE=18900 scripts/gate.sh
#   scripts/gate.sh --only pytest,evals      scripts/gate.sh --skip playwright,smoke --coverage
#
# It refuses to run without SCENE_TEST_DATABASE_URL, or when it names the studio's database `scene`; two gates on one
# test database never run at once (a lock folder in the temp folder with the holder's process id); the URL is never
# printed, and each step's log has it taken out. SCENE_TEST_PORT_BASE (default 8100) goes on to the test studios.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STEPS="typecheck lint tokens unit pytest order evals build mobile playwright smoke models"
ONLY="" SKIP="" MODELS=0 COVERAGE=0 STOP=0 LOGDIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY="${2//,/ }"; shift 2 ;;
    --skip) SKIP="${2//,/ }"; shift 2 ;;
    --models) MODELS=1; shift ;;
    --coverage) COVERAGE=1; shift ;;
    --stop-on-failure) STOP=1; shift ;;
    --log-dir) LOGDIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option $1" >&2; exit 2 ;;
  esac
done
for name in $ONLY $SKIP; do
  case " $STEPS " in *" $name "*) ;; *) echo "No step '$name'. The steps: $STEPS" >&2; exit 2 ;; esac
done

# ------------------------------------------------------------------ the test database: never the live one, one gate at a time
URL="${SCENE_TEST_DATABASE_URL:-}"
if [ -z "$URL" ]; then
  echo "The gate needs SCENE_TEST_DATABASE_URL: a test database it may empty, postgresql://scene_test:<password>@localhost:5432/scene_test_<name> (docs/database.md)." >&2
  exit 2
fi
REST="${URL#*://}"; HOSTPART="${REST%%/*}"; DATABASE="${REST#*/}"; DATABASE="${DATABASE%%\?*}"
[ "$HOSTPART" = "$REST" ] && DATABASE=""
HOSTPORT="${HOSTPART##*@}"; USERINFO="${HOSTPART%@*}"; [ "$USERINFO" = "$HOSTPART" ] && USERINFO=""
SECRET=""; case "$USERINFO" in *:*) SECRET="${USERINFO#*:}" ;; esac
if [ -z "$DATABASE" ] || [ "$DATABASE" = "scene" ]; then
  echo "SCENE_TEST_DATABASE_URL names the studio's live database (or none). The gate empties every table: point it at a test database." >&2
  exit 2
fi
PORT_BASE="${SCENE_TEST_PORT_BASE:-8100}"
case "$PORT_BASE" in ''|*[!0-9]*) echo "SCENE_TEST_PORT_BASE must be a number." >&2; exit 2 ;; esac
for offset in 81 90 99 181 190 199; do
  port=$((PORT_BASE + offset))
  case " 8080 8081 8090 3000 5432 8188 " in *" $port "*)
    echo "SCENE_TEST_PORT_BASE $PORT_BASE puts a test studio on $port, which the live studio or its services use." >&2; exit 2 ;; esac
done
export SCENE_TEST_PORT_BASE="$PORT_BASE"

TMPROOT="${TMPDIR:-${TEMP:-/tmp}}"
# Git Bash gives TEMP as C:\Users\...: as C:/Users/... the step commands keep it (backslashes would be lost)
command -v cygpath >/dev/null 2>&1 && TMPROOT="$(cygpath -m "$TMPROOT")"
KEY="$(printf '%s_%s' "${HOSTPORT/:/_}" "$DATABASE" | tr -c 'A-Za-z0-9_.-' '_')"
LOCKROOT="$TMPROOT/scene-gate-locks"; mkdir -p "$LOCKROOT"
LOCK="$LOCKROOT/$KEY.lock"
MYPID="$$"; [ -r "/proc/$$/winpid" ] && MYPID="$(cat /proc/$$/winpid)"   # Git Bash: the Windows id, as gate.ps1 writes it
alive() {   # is the process with this id (a Windows id under Git Bash) still running?
  [ -n "$1" ] || return 1
  if [ -r "/proc/$$/winpid" ]; then tasklist //FI "PID eq $1" 2>/dev/null | grep -q " $1 "; else kill -0 "$1" 2>/dev/null; fi
}
if ! mkdir "$LOCK" 2>/dev/null; then
  holder="$(cat "$LOCK/pid" 2>/dev/null | tr -d '\r\n ')"
  if alive "$holder"; then
    echo "Another gate (process $holder) is using the database $DATABASE. Wait for it, or give this one a database of its own." >&2
    exit 3
  fi
  rm -rf "${LOCK:?}"   # left by a gate that is gone
  mkdir "$LOCK" 2>/dev/null || { echo "Another gate took the database $DATABASE just now." >&2; exit 3; }
fi
echo "$MYPID" > "$LOCK/pid"
trap 'rm -rf "${LOCK:?}"' EXIT INT TERM

# ------------------------------------------------------------------ the steps
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PY="$ROOT/.venv/Scripts/python.exe"; else PY="$ROOT/.venv/bin/python"; fi
[ -n "$LOGDIR" ] || LOGDIR="$TMPROOT/scene-gate/$KEY/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOGDIR"
COV=""
[ "$COVERAGE" = 1 ] && COV="--cov=scene --cov=evals --cov-report=term --cov-report=json:$LOGDIR/coverage.json"

command_of() {   # dir|command of a step
  case "$1" in
    typecheck) echo "$ROOT|npm run typecheck" ;;
    lint) echo "$ROOT|npm run lint" ;;
    tokens) echo "$ROOT|npm run tokens:check" ;;
    unit) echo "$ROOT|npm test" ;;
    pytest) echo "$ROOT/backend|$PY -m pytest -q -p no:cacheprovider $COV" ;;
    # one file's tests must never depend on another's having run first: these two, in the order that once failed
    order) echo "$ROOT/backend|$PY -m pytest -q -p no:cacheprovider tests/test_claude_sdk.py tests/test_claude.py" ;;
    evals) echo "$ROOT/backend|$PY -m evals.run --json $LOGDIR/evals.json" ;;
    build) echo "$ROOT|npm run build -w apps/web" ;;
    mobile) echo "$ROOT|npm run build -w apps/mobile" ;;
    playwright) echo "$ROOT/apps/web|npx playwright test" ;;
    smoke) echo "$ROOT|node apps/web/tests/smoke/smoke.mjs --fake-comfy" ;;
    models) echo "$ROOT|$PY scripts/check_models.py" ;;
  esac
}

says_of() {   # the step's numbers, from its log
  case "$1" in
    pytest|order) grep -E '[0-9]+ (passed|failed)' "$2" | tail -1 | sed 's/=//g; s/^ *//; s/ *$//' ;;
    evals) grep -E '^evals: ' "$2" | tail -1 ;;
    unit) printf 'passed: %s' "$(grep -oE 'Tests:? +([0-9]+ failed, )?[0-9]+ passed' "$2" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' | paste -sd/ -)" ;;
    build) grep -E 'First-load JavaScript' "$2" | tail -1 ;;
    playwright) grep -E '^ *[0-9]+ (passed|failed)' "$2" | tail -1 | sed 's/^ *//' ;;
    smoke) grep -oE '[0-9]+ passed, [0-9]+ failed' "$2" | tail -1 ;;
  esac
}

scrub() {   # the URL and its password out of a log
  local file="$1"
  "$PY" - "$file" <<'PY'
import os, sys
path = sys.argv[1]
url = os.environ.get("SCENE_TEST_DATABASE_URL", "")
text = open(path, encoding="utf-8", errors="replace").read()
if url:
    text = text.replace(url, "<SCENE_TEST_DATABASE_URL>")
    rest = url.split("://", 1)[-1].split("@", 1)
    if len(rest) == 2 and ":" in rest[0]:
        text = text.replace(rest[0].split(":", 1)[1], "<password>")
open(path, "w", encoding="utf-8").write(text)
PY
}

ROWS=""; FAILED=0
for name in $STEPS; do
  why=""
  if [ -n "$ONLY" ] && ! case " $ONLY " in *" $name "*) true ;; *) false ;; esac; then why="not asked"
  elif case " $SKIP " in *" $name "*) true ;; *) false ;; esac; then why="skipped (--skip)"
  elif [ "$name" = models ] && [ "$MODELS" != 1 ]; then why="off (--models: it calls Claude for real)"
  elif [ "$name" = mobile ] && [ -f "$ROOT/apps/mobile/dist/index.html" ]; then why="already built"
  elif [ "$FAILED" = 1 ] && [ "$STOP" = 1 ]; then why="not run (a step before failed)"
  fi
  if [ -n "$why" ]; then ROWS="$ROWS$name|SKIP||$why"$'\n'; continue; fi
  echo "==> $name"
  spec="$(command_of "$name")"; dir="${spec%%|*}"; cmd="${spec#*|}"
  log="$LOGDIR/$name.log"; started=$(date +%s)
  (cd "$dir" && eval "$cmd") > "$log" 2>&1; code=$?
  scrub "$log"
  seconds=$(( $(date +%s) - started ))
  says="$(says_of "$name" "$log")"
  if [ "$code" = 0 ]; then result=PASS; else result=FAIL; FAILED=1; tail -25 "$log"; says="exit $code; $says (log: $log)"; fi
  ROWS="$ROWS$name|$result|$seconds|$says"$'\n'
done

echo
echo "Gate on database $DATABASE, ports from $PORT_BASE; logs in $LOGDIR"
printf '%-11s %-6s %-7s %s\n' Step Result Seconds Says
printf '%s' "$ROWS" | while IFS='|' read -r step result seconds says; do
  [ -n "$step" ] && printf '%-11s %-6s %-7s %s\n' "$step" "$result" "$seconds" "$says"
done
if [ "$FAILED" = 1 ]; then echo "The gate FAILED."; exit 1; fi
echo "The gate passed."

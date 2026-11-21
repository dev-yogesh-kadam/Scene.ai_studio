@echo off
rem Start Scene.ai on Windows. The first run creates a Python environment in .venv.
cd /d "%~dp0.."
rem Langfuse (C:\Scene\langfuse) starts beside the studio, in a small window of its own, so the studio does not wait for
rem Docker. SCENE_NO_LANGFUSE=1 leaves it off (scripts\start.langfuse.bat).
if not "%SCENE_NO_LANGFUSE%"=="1" start "Langfuse" /min cmd /c scripts\start.langfuse.bat
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv 2>nul || python -m venv .venv || goto :fail
)
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r backend\requirements.txt || goto :fail
if not exist config.json copy config.example.json config.json >nul
rem Motion graphics need Node.js. Without it the studio still runs; that section just says what is missing.
rem npm ls fails when what is installed is not what package.json pins (a new HyperFrames): it is installed again then.
where node >nul 2>nul && ( pushd motion & ( call npm ls --depth=0 >nul 2>nul || call npm install --no-audit --no-fund ) & popd )
rem HyperFrames renders in a Chrome of its own: fetched here the first time (about 150 MB), not in the middle of a
rem user's first render. Once it is there this takes a moment and needs no network.
set HYPERFRAMES_NO_TELEMETRY=1
set HYPERFRAMES_NO_UPDATE_CHECK=1
where node >nul 2>nul && if exist motion\node_modules\hyperframes\bin\hyperframes.mjs ( node motion\node_modules\hyperframes\bin\hyperframes.mjs browser ensure >nul 2>nul || echo HyperFrames could not fetch its Chrome now: the first motion graphics render will. )
rem The packages of the web studio and the phone site are installed once at the root (npm workspaces: apps/*,
rem packages/*), and again when package-lock.json or a package.json changed (after a git pull).
where node >nul 2>nul && ( node scripts\start.stale.mjs packages && call npm install --no-audit --no-fund )
rem The phone site (/m/, apps/mobile) and the studio with the admin console (apps/web) are built when there is no build
rem yet or a file they are built from changed after it.
where node >nul 2>nul && ( node scripts\start.stale.mjs mobile && call npm run build -w apps/mobile )
where node >nul 2>nul && ( node apps\web\scripts\stale.mjs && call npm run build -w apps/web )
rem Each line the studio prints reaches the window, or a file its output is sent to, at once (not when a buffer fills).
set PYTHONUNBUFFERED=1
cd backend
..\.venv\Scripts\python.exe -m scene
:fail
pause

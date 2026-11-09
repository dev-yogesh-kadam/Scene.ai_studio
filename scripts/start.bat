@echo off
rem Start Scene.ai on Windows. The first run creates a Python environment in .venv.
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv 2>nul || python -m venv .venv || goto :fail
)
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r backend\requirements.txt || goto :fail
if not exist config.json copy config.example.json config.json >nul
rem Motion graphics need Node.js. Without it the studio still runs; that section just says what is missing.
rem npm ls fails when what is installed is not what package.json pins (a new HyperFrames): it is installed again then.
where node >nul 2>nul && ( pushd motion & ( call npm ls --depth=0 >nul 2>nul || call npm install --no-audit --no-fund ) & popd )
rem The phone site (/m/) is built from mobile/ the first time; after a change to it, run "npm run build" there.
where node >nul 2>nul && if not exist mobile\dist\index.html ( pushd mobile & ( if not exist node_modules call npm install --no-audit --no-fund ) & call npm run build & popd )
cd backend
..\.venv\Scripts\python.exe -m scene
:fail
pause

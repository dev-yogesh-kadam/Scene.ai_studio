@echo off
rem Start Langfuse (langfuse\ in the repo, docs/langfuse.md) for start.bat, in a window of its own so the studio does not
rem wait for it. Starts Docker Desktop when its engine is not answering, waits for it (at most 3 minutes), then
rem "docker compose up -d". Langfuse is optional: anything missing is said here and the studio runs on without it
rem (what it sends waits in its queue until Langfuse answers).
rem The folder is ..\langfuse from this script (the repo's langfuse\), or SCENE_LANGFUSE_DIR when it is set.
setlocal
set "LF=%SCENE_LANGFUSE_DIR%"
if "%LF%"=="" set "LF=%~dp0..\langfuse"
if not exist "%LF%\docker-compose.yml" ( echo Langfuse: no docker-compose.yml in %LF%; not started. & goto :done )

set "DOCKER=docker"
where docker >nul 2>nul || set "DOCKER=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
if not "%DOCKER%"=="docker" if not exist "%DOCKER%" ( echo Langfuse: Docker is not installed; not started. & goto :done )

"%DOCKER%" info >nul 2>nul && goto :up
set "DESKTOP=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
if not exist "%DESKTOP%" set "DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DESKTOP%" ( echo Langfuse: Docker Desktop was not found; start it, then run this again. & goto :done )
echo Langfuse: starting Docker Desktop...
start "" "%DESKTOP%"
set /a TRIES=0
:wait
set /a TRIES+=1
if %TRIES% gtr 36 ( echo Langfuse: Docker did not start within 3 minutes; not started. & goto :done )
rem five seconds (ping, not timeout: timeout fails when the window has no keyboard)
ping -n 6 127.0.0.1 >nul
"%DOCKER%" info >nul 2>nul || goto :wait

:up
echo Langfuse: starting its containers...
pushd "%LF%"
"%DOCKER%" compose up -d
set RC=%ERRORLEVEL%
popd
if not "%RC%"=="0" ( echo Langfuse: docker compose failed ^(code %RC%^). & goto :done )
echo Langfuse: up. It answers on http://localhost:3000 in about a minute.
endlocal
exit /b 0

:done
endlocal
echo This window can be closed.
pause
exit /b 1

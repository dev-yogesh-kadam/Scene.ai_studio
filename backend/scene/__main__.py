"""Run the app:  python -m scene  (from the backend folder).

One server listens on two ports: the studio's, and the admin console's (main.Doors sends each request to its site).
"""

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import uvicorn

from .config import load_settings
from .logs import configure as configure_logs
from .main import Doors, create_app


def listen(host, port):
    try:
        return socket.create_server((host, port), family=socket.AF_INET6 if ":" in host else socket.AF_INET)
    except OSError as e:
        sys.exit("Scene.ai can't listen on {}:{} ({}). Is it running already?".format(host, port, e.strerror or e))


def stop_langfuse():
    """Langfuse's containers (scripts\\start.langfuse.bat starts them beside the studio) stop when the studio stops, so
    nothing of the studio's is left running. "stop", not "down": its traces and settings are kept for the next start.
    SCENE_NO_LANGFUSE=1 (Langfuse never started by the studio) leaves them alone."""
    if os.environ.get("SCENE_NO_LANGFUSE") == "1":
        return
    folder = Path(os.environ.get("SCENE_LANGFUSE_DIR") or Path(__file__).resolve().parents[2] / "langfuse")
    if not (folder / "docker-compose.yml").is_file():
        return
    docker = shutil.which("docker") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe")
    if not Path(docker).is_file():
        return
    print("Stopping Langfuse...", flush=True)
    # Its own process group, away from this console: a second Ctrl+C (or "Terminate batch job? Y") used to reach docker
    # too and kill it half-way (web and worker stopped, postgres, clickhouse, redis and minio left running).
    flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0
    try:
        stopping = subprocess.Popen([docker, "compose", "stop"], cwd=folder, creationflags=flags,
                                    start_new_session=os.name != "nt", stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        print("Langfuse could not be stopped: stop it with \"docker compose stop\" in {}.".format(folder))
        return
    try:
        stopping.wait(timeout=120)
        print("Langfuse stopped.")
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        print("Langfuse keeps stopping in the background.")


settings = load_settings()
configure_logs(settings.log_format)
app = create_app(settings)
sockets = [listen(settings.host, settings.port)]
print("Scene.ai is running at http://localhost:{}".format(settings.port))
if app.state.console is not None:
    # console_host may name several addresses, comma-separated: this PC's own and its Tailscale one, say.
    for host in [h.strip() for h in settings.console_host.split(",") if h.strip()]:
        sockets.append(listen(host, settings.console_port))
        shown = "localhost" if host in ("127.0.0.1", "::1", "0.0.0.0", "::") else host
        print("The admin console is at http://{}:{}".format(shown, settings.console_port))
try:
    uvicorn.Server(uvicorn.Config(Doors(app), log_level="warning")).run(sockets=sockets)
except KeyboardInterrupt:
    pass   # Ctrl+C is how the studio is stopped: no traceback for it
finally:
    stop_langfuse()

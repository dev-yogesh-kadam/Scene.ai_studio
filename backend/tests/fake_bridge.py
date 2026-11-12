"""A fake LUFI bridge for the tests (test_claude_connection.py): the protocol of docs/servers.md, served on a port of
this machine, running the fake `claude` (fixtures/fake_claude.py) as the real bridge runs Claude Code: in one folder
that never changes, with the system prompt's text written to a file of its own.

Every run is checked against the contract the studio and the bridge share (contract_problem), so a test that runs
through it also proves the studio keeps to it: a flag or variable the bridge would not take is refused."""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
WITH_VALUE = {"--input-format", "--output-format", "--model", "--tools", "--allowedTools", "--setting-sources", "--max-turns",
              "--settings", "--effort", "--resume", "--json-schema", "--mcp-config"}
BARE = {"-p", "-v", "--version", "--verbose", "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"}
WEB = {"WebSearch"}
VARIABLES = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY"}
SETTINGS = {"autoMemoryEnabled", "autoCompactWindow"}


def contract_problem(args, env):
    """What in a start frame the bridge would refuse ("refused"), or None: the allowed flags and their values, as
    the studio and the bridge agreed them, and only the "no memory" variable."""
    values, at = {}, 0
    while at < len(args):
        arg = args[at]
        if arg in BARE:
            at += 1
        elif arg in WITH_VALUE and at + 1 < len(args):
            values[arg] = args[at + 1]
            at += 2
        else:
            return "the argument {!r}".format(arg)
    if set(env) - VARIABLES:
        return "the variables {}".format(sorted(set(env) - VARIABLES))
    if any(arg.startswith("--") and "=" in arg for arg in args):
        return "a --flag=value"
    if values.get("--tools") and set(values["--tools"].split(",")) - WEB:
        return "--tools " + values["--tools"]
    try:
        servers = json.loads(values.get("--mcp-config") or '{"mcpServers": {}}')["mcpServers"]
        settings = json.loads(values.get("--settings") or "{}")
    except (ValueError, KeyError, TypeError):
        return "--mcp-config or --settings that is not JSON"
    if any(not isinstance(s, dict) or s.get("type") != "sdk" for s in servers.values()):
        return "--mcp-config with a server that is not the studio's own"
    if set(settings) - SETTINGS:
        return "--settings {}".format(sorted(set(settings) - SETTINGS))
    for tool in filter(None, re.split(r"[,\s]+", values.get("--allowedTools") or "")):
        named = re.fullmatch(r"mcp__([A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*)__[A-Za-z0-9_-]+", tool)   # no wildcards
        if tool not in WEB and not (named and named.group(1) in servers):
            return "--allowedTools " + tool
    return None


class FakeBridge:
    """The bridge, on a free port of 127.0.0.1, until stop(). refuse: the error code the next run is refused with;
    health: what /health says; starts: every start frame; forgotten: the sessions /forget was asked to remove."""

    def __init__(self, key="bridge-key"):
        self.key, self.refuse, self.starts, self.forgotten = key, None, [], []
        self.health = {"up": True, "enabled": True, "signed_in": True, "plan": "max", "claude_version": "2.1.310",
                       "bridge_version": "0.1.0", "calls_now": 0, "limit": 4, "last_error": "", "uptime_s": 1}
        self.folder = tempfile.mkdtemp(prefix="fake-bridge-")   # the one folder every run is in
        app = FastAPI()
        app.add_api_websocket_route("/run", self._run)
        app.add_api_route("/health", self._health, methods=["GET"])
        app.add_api_route("/forget", self._forget, methods=["POST"])
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        while not self.server.started:
            time.sleep(0.02)
        self.url = "http://127.0.0.1:{}".format(self.server.servers[0].sockets[0].getsockname()[1])

    def stop(self):
        self.server.should_exit = True
        self.thread.join(10)

    def _keyed(self, headers):
        return headers.get("authorization") == "Bearer " + self.key

    async def _health(self, request: Request):
        if not self._keyed(request.headers):
            return JSONResponse({"type": "error", "code": "bad_key", "message": "wrong key"}, status_code=401)
        return self.health

    async def _forget(self, request: Request):
        if not self._keyed(request.headers):
            return JSONResponse({"type": "error", "code": "bad_key", "message": "wrong key"}, status_code=401)
        self.forgotten.append((await request.json())["session_id"])
        return {"ok": True}

    async def _run(self, socket: WebSocket):
        await socket.accept()

        async def refuse(code, message):
            await socket.send_text(json.dumps({"type": "error", "code": code, "error": message}))
            await socket.close()
        if not self._keyed(socket.headers):
            return await refuse("bad_key", "That is not the bridge's key.")
        start = json.loads(await socket.receive_text())
        self.starts.append(start)
        if self.refuse:
            code, self.refuse = self.refuse, None
            return await refuse(code, "Refused for the test: " + code)
        problem = contract_problem(start["args"], start.get("env") or {})
        if problem:
            return await refuse("refused", "The bridge does not take " + problem)
        args = list(start["args"])
        if start.get("system_prompt") is not None:   # the bridge writes it to a file of its own and gives claude that
            prompt = Path(self.folder) / "system-{}.txt".format(len(self.starts))
            prompt.write_text(start["system_prompt"], encoding="utf-8")
            args += ["--system-prompt-file", str(prompt)]
        await socket.send_text(json.dumps({"type": "started"}))
        process = subprocess.Popen([sys.executable, str(FAKE_CLAUDE), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=self.folder, env={**os.environ, **(start.get("env") or {})})
        loop, pieces = asyncio.get_running_loop(), asyncio.Queue()

        def pump(name, stream):
            while True:
                chunk = os.read(stream.fileno(), 65536)
                if chunk:
                    loop.call_soon_threadsafe(pieces.put_nowait, (name, chunk))
                else:
                    loop.call_soon_threadsafe(pieces.put_nowait, (name, None))
                    return
        for name in ("stdout", "stderr"):
            threading.Thread(target=pump, args=(name, getattr(process, name)), daemon=True).start()

        async def listen():   # the studio's stdin: binary frames, then {"type": "eof"}; a closed socket ends the run
            try:
                while True:
                    message = await socket.receive()
                    if message["type"] == "websocket.disconnect":
                        raise WebSocketDisconnect()
                    if message.get("bytes") is not None:
                        process.stdin.write(message["bytes"])
                        process.stdin.flush()
                    elif json.loads(message["text"]) == {"type": "eof"}:
                        process.stdin.close()
                    else:
                        raise ValueError("after start, the only text frame is eof")
            except (WebSocketDisconnect, RuntimeError, OSError, ValueError):
                if process.poll() is None:
                    process.kill()
        listening = asyncio.ensure_future(listen())
        ended = 0
        try:
            while ended < 2:
                name, text = await pieces.get()
                if text is None:
                    ended += 1
                else:
                    await socket.send_bytes((b"" if name == "stdout" else b"") + text)   # bytes, as read
            code = await asyncio.to_thread(process.wait)
            await socket.send_text(json.dumps({"type": "exit", "code": code}))
            await socket.close()
        except (WebSocketDisconnect, RuntimeError):
            if process.poll() is None:
                process.kill()
        finally:
            listening.cancel()

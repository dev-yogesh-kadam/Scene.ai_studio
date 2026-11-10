"""The hardening of 10 November 2026: sign-up closed until an admin opens it, the limits of the expensive paths, the admin
console kept off the studio's (public) port, and an audit log whose seals hold when entries are written together."""

import json
import threading
from types import SimpleNamespace

from scene import audit, security
from scene.config import ROOT, Settings, load_settings


def account(client, email="ada@example.com", password="correct horse", **extra):
    client.cookies.clear()
    return client.post("/api/auth/register", json={"email": email, "password": password, **extra})


# ---------------------------------------------------------------- sign-up

def test_a_fresh_installation_keeps_sign_up_closed_and_gives_no_free_credits(tmp_path):
    defaults = Settings()
    assert defaults.allow_signup is False and defaults.signup_credits == 0 and defaults.signup_invite == ""
    # A config.json made from the example does not open it either; nor does a config.json that says nothing.
    example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    assert example.get("allow_signup") is False and not example.get("signup_credits")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert load_settings(tmp_path / "config.json").allow_signup is False


def test_only_the_first_account_is_made_while_sign_up_is_closed(client):
    client.app.state.settings.allow_signup = False     # as on a fresh installation (the tests' own setting opens it)
    assert client.get("/api/auth/state").json() == {"first_run": True, "signup_open": True}
    assert account(client).status_code == 200            # the first account, the admin
    assert client.get("/api/auth/state").json() == {"first_run": False, "signup_open": False}
    refused = account(client, "eve@example.com")
    assert refused.status_code == 403 and "closed" in refused.json()["detail"]
    # An admin opens it in the console's Settings, which wins over config.json.
    client.app.state.db.set_setting("allow_signup", "1")
    assert account(client, "eve@example.com").status_code == 200


def test_an_invite_code_is_asked_for_when_one_is_set(client):
    client.app.state.settings.signup_invite = "seven-ravens"
    assert account(client).status_code == 200            # the first account needs none
    assert client.get("/api/auth/state").json() == {"first_run": False, "signup_open": True, "invite_required": True}
    assert account(client, "eve@example.com").status_code == 403
    assert account(client, "eve@example.com", invite="seven-crows").status_code == 403
    assert account(client, "eve@example.com", invite=" seven-ravens ").status_code == 200
    entries = client.app.state.db.all("SELECT action, detail FROM audit_log WHERE action = 'Refused a new account'")
    assert len(entries) == 2 and all("invite" in e["detail"] for e in entries)


def test_a_new_account_starts_with_the_credits_the_studio_gives(client):
    assert account(client).json()["credits"] == 500      # the tests' signup_credits
    client.app.state.settings.signup_credits = 0
    assert account(client, "eve@example.com").json()["credits"] == 0


# ---------------------------------------------------------------- rate limits

def test_the_expensive_paths_are_limited_per_user(client):
    account(client)
    limit = security.LIMITS
    for path, name in (("/api/library/import", "import"), ("/api/agent/plans", "plan"), ("/api/edit/film", "render")):
        answers = [client.post(path, json={}).status_code for _ in range(limit[name][0] + 1)]
        assert 429 not in answers[:-1] and answers[-1] == 429, (path, answers[-3:])
    over = client.post("/api/edit/film", json={})
    assert over.status_code == 429 and int(over.headers["retry-after"]) >= 1
    # Another user has counts of their own.
    account(client, "eve@example.com")
    assert client.post("/api/edit/film", json={}).status_code != 429


def test_an_agent_tool_can_ask_whether_its_user_is_over_the_limit(client):
    import asyncio
    from scene.api.deps import allowed
    state = client.app.state
    most = security.LIMITS["page_build"][0]

    async def ask(user_id, times):
        return [await allowed(state, "page_build", user_id) for _ in range(times)]
    answers = asyncio.run(ask(1, most + 1))
    assert all(answers[:-1]) and answers[-1] is False
    assert asyncio.run(ask(2, 1)) == [True]


# ---------------------------------------------------------------- the admin console

def call(app, path, port, host):
    """One request to `app` as it arrives on a socket listening on `port`, whatever its Host header says."""
    answer = {}

    async def run():
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                 "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
                 "headers": [(b"host", host.encode())], "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", port)}
        sent = False

        async def receive():
            nonlocal sent
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                answer["status"] = message["status"]
            elif message["type"] == "http.response.body":
                answer["body"] = answer.get("body", b"") + message.get("body", b"")
        await app(scope, receive, send)
    import asyncio
    asyncio.run(run())
    return answer


def test_the_admin_console_is_never_on_the_studios_port(client):
    """The tunnel reaches the studio's port only. Whatever Host a visitor sends through it, no console route, page or
    script answers there; the console listens on this machine alone unless console_host says otherwise."""
    from scene.main import Doors, create_console
    assert Settings().console_host == "127.0.0.1" and Settings().console_port != Settings().port
    settings = client.app.state.settings
    doors = Doors(client.app)
    for host in ("developmenttestinghere.in", "127.0.0.1:{}".format(settings.console_port), "localhost:{}".format(settings.console_port)):
        for path in ("/api/admin/users", "/api/console/me", "/console.html", "/_app/console-XyZ789.js"):
            assert call(doors, path, settings.port, host)["status"] == 404, (host, path)
    # On the console's own port it answers (signed out: 401).
    assert call(doors, "/api/admin/users", settings.console_port, "127.0.0.1")["status"] == 401
    # The console can't share the studio's port.
    import pytest
    same = SimpleNamespace(state=SimpleNamespace(settings=Settings(port=8080, console_port=8080)))
    with pytest.raises(ValueError):
        create_console(same)


# ---------------------------------------------------------------- the audit log and sign-in settings

def test_audit_entries_written_together_keep_the_chain_whole(client):
    request = SimpleNamespace(app=client.app, client=SimpleNamespace(host="127.0.0.1"), headers={})
    errors = []

    def write(n):
        try:
            for i in range(8):
                audit.record(request, None, "Test", "thread {}".format(n), str(i))
        except Exception as error:   # pragma: no cover - shown by the assert
            errors.append(error)
    threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    checked = audit.verify(client.app.state.db)
    assert checked["ok"] is True and checked["sealed"] >= 64, checked


def test_changing_the_password_and_turning_off_two_step_sign_in_are_logged(client):
    import time
    account(client)
    assert client.put("/api/auth/password", json={"current": "correct horse", "new": "a better one"}).status_code == 200
    secret = client.post("/api/auth/mfa/setup", json={"password": "a better one"}).json()["secret"]
    now = int(time.time() // security.TOTP_STEP)
    assert client.post("/api/auth/mfa/enable", json={"code": security.totp_code(secret, now)}).status_code == 200
    off = client.post("/api/auth/mfa/disable", json={"password": "a better one", "code": security.totp_code(secret, now + 1)})
    assert off.status_code == 200
    actions = [r["action"] for r in client.app.state.db.all("SELECT action FROM audit_log ORDER BY id")]
    assert "Changed password" in actions and "Turned off two-step sign-in" in actions


# ---------------------------------------------------------------- the image

def test_the_image_runs_as_its_own_account_with_no_secret_in_it():
    """A static check of the Dockerfile and the build context's exclusions (building the image is not needed)."""
    import re
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    users = re.findall(r"(?m)^USER\s+(\S+)", dockerfile)
    assert users and users[-1] not in ("root", "0")                          # the last USER, the one that runs the app
    assert dockerfile.rfind("USER ") > dockerfile.rfind("RUN ")              # nothing runs as root after it
    for line in re.findall(r"(?m)^(?:ENV|ARG)\s.*$", dockerfile):            # no password or key baked into a layer
        assert not re.search(r"(PASSWORD|_KEY|TOKEN|SECRET)[A-Z_]*=(?!/)\S", line), line
    ignored = set((ROOT / ".dockerignore").read_text(encoding="utf-8").split("\n"))
    for pattern in ("config.json", "secret.key", "scene.env", "docs", "**/config.json", "**/secret.key", "**/scene.env",
                    "**/*.mp4", "**/*.mov", "**/.env"):
        assert pattern in ignored, pattern

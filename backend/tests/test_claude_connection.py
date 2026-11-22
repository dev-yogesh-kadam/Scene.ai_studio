"""The Claude connection (claude.py's LocalProgram, claude_connection.py): the studio runs the `claude` of this PC, on
the account it is signed in with (Claude on this PC) or with an Anthropic API key, switched in the console with no
restart. What only Claude on this PC does (the policy, the sign-in, the plan's limits, the guard): test_claude_local.py.

Claude Code is a fake `claude` (fixtures/fake_claude.py), run by the studio itself. Nothing here reaches Anthropic or
this machine's own Claude Code."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scene import claude, claude_connection, vault
from scene.config import Settings

sdk = pytest.importorskip("claude_agent_sdk")

FAKE_CLAUDE = Path(__file__).resolve().parent / "fixtures" / "fake_claude.py"
MESSAGES = [{"role": "system", "content": "You answer in JSON."}, {"role": "user", "content": "hi"}]
SCHEMA = {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"]}
API_KEY = "sk-ant-test-0123456789"


@pytest.fixture
def fake_claude(monkeypatch, tmp_path):
    """The fake `claude` in place of Claude Code here; returns the file its runs are written down in."""
    log = tmp_path / "runs.jsonl"
    monkeypatch.setattr(claude, "find", lambda: str(FAKE_CLAUDE))
    monkeypatch.setattr(claude, "RUN_WITH", (sys.executable,))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    for name in ("FAKE_CLAUDE_SAY", "FAKE_CLAUDE_AUTH", "FAKE_CLAUDE_LIMITS", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return log


@pytest.fixture(params=["api_key", "this_pc"])
def connection(request, fake_claude):
    """Each test with it runs once with each connection: (mode, the key `claude` should be given, the runs' file)."""
    key = API_KEY if request.param == "api_key" else ""
    claude.CONNECTION = {"mode": request.param, "api_key": key}
    return SimpleNamespace(mode=request.param, key=key or None, log=fake_claude)


def service(tmp_path):
    return {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": ["sonnet"], "only": "", "cli": "claude",
            "timeout": 60, "fast": "", "home": str(tmp_path / "home"), "window": 1_000_000}


def runs(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []


def converse(s, text, thread, tools=None):
    async def find_assets(call):
        return "item 7: " + call["query"]
    tools = {"find_assets": find_assets} if tools is None else tools
    return claude.converse(s, "sonnet", "You plan.", text, SCHEMA, thread, tools, {"find_assets": ("Find assets.", {"query": str})},
                           "Answer now.", 4)


# ---------------------------------------------------------------- both connections

def test_a_call_of_its_own_goes_by_the_connection_in_use(connection, tmp_path):
    answer, tokens, _ = asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    assert json.loads(answer) == {"reply": "hello"} and tokens["answer"] == 5
    [run] = runs(connection.log)
    assert run["system"].startswith("You answer in JSON.") and run["memory"] == "1"
    assert "@system_prompt" not in run["args"] and "--no-session-persistence" in run["args"]
    assert run["api_key"] == connection.key and run["cwd"] != str(tmp_path / "home")   # a thrown-away folder of its own
    assert claude.RUNNING["now"] == 0


def test_a_picture_reaches_claude_code(connection, tmp_path):
    answer, _, _ = asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA, images=["AAAA"]))
    assert json.loads(answer) == {"reply": "seen 1 pictures"}
    picture = runs(connection.log)[0]["messages"][0]["content"][-1]
    assert picture == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}


def test_a_live_session_calls_the_studios_own_tool_in_process(connection, tmp_path):
    s, called = service(tmp_path), []

    async def find_assets(call):
        called.append(call)
        return "item 7: Mira"

    async def go():
        thread = {"key": "1:tab1:3", "id": None}
        try:
            answer, _, _, tools = await converse(s, "please call find_assets", thread, {"find_assets": find_assets})
            again, _, _, _ = await converse(s, "and again, hi", thread, {"find_assets": find_assets})
            return answer, tools, again, thread
        finally:
            await claude.close_all()
    answer, tools, again, thread = asyncio.run(go())
    assert json.loads(answer) == {"reply": "the tool said: item 7: Mira"} and called == [{"query": "Mira"}] and tools == ["find_assets"]
    assert json.loads(again) == {"reply": "hello"} and thread["id"] == "fake-session-1"
    [run] = runs(connection.log)   # one program for both messages, which wrote down its run as it ended
    assert len(run["messages"]) == 2 and run["memory"] == "1" and run["api_key"] == connection.key
    args = run["args"]
    assert args[args.index("--allowedTools") + 1] == "mcp__studio__find_assets"   # the studio's tool, in-process


def test_compact_and_rename_go_on_stdin(connection, tmp_path):
    thread = {"key": "k", "id": "fake-session-1"}
    assert asyncio.run(claude.compact(service(tmp_path), thread)) == 9000
    [run] = runs(connection.log)
    assert run["messages"] == [{"role": "user", "content": "/compact"}] and "/compact" not in run["args"]
    assert run["args"][run["args"].index("--resume") + 1] == "fake-session-1"


def test_claude_codes_version_here_needs_no_key(fake_claude):
    claude.CONNECTION = {"mode": "api_key", "api_key": ""}
    assert asyncio.run(claude_connection.version()) == "2.1.310"


def test_signed_out_and_missing_claude_code(connection, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SAY", "signed_out")
    said = "not signed in: the Anthropic API key" if connection.mode == "api_key" else "Claude Code on this PC is not signed in"
    with pytest.raises(claude.Failed, match=said):
        asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    monkeypatch.setattr(claude, "find", lambda: "")
    with pytest.raises(claude.Failed, match="not installed on this PC"):
        asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))


def test_a_deleted_conversations_session_is_forgotten_here(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    s = service(tmp_path)
    kept = tmp_path / "claude-home" / "projects" / "".join(c if c.isalnum() else "-" for c in str(Path(s["home"]).resolve()))
    kept.mkdir(parents=True)
    (kept / "0b6c1f0e-1111-2222-3333-444455556666.jsonl").write_text("{}", encoding="utf-8")
    (kept / "other-session-0001.jsonl").write_text("{}", encoding="utf-8")
    claude.forget(s, "0b6c1f0e-1111-2222-3333-444455556666")
    claude.forget(s, "../other-session-0001")   # never a path
    assert sorted(p.name for p in kept.iterdir()) == ["other-session-0001.jsonl"]


# ---------------------------------------------------------------- the API key's health

def test_the_api_keys_health(fake_claude, monkeypatch):
    asked = []

    def answer(request):
        asked.append(request)
        return httpx.Response(200 if request.headers["x-api-key"] == API_KEY else 401, json={"data": []})
    real = httpx.AsyncClient
    monkeypatch.setattr(claude_connection.httpx, "AsyncClient", lambda **k: real(transport=httpx.MockTransport(answer), **k))
    claude.CONNECTION = {"mode": "api_key", "api_key": ""}
    assert "Paste an Anthropic API key" in asyncio.run(claude_connection.status())["detail"] and not asked
    claude.CONNECTION["api_key"] = API_KEY
    found = asyncio.run(claude_connection.status())
    assert found["online"] is True and found["key_works"] is True and found["claude_version"] == "2.1.310"
    assert str(asked[0].url).endswith("/v1/models?limit=1") and found["testing"] == ""
    claude.CONNECTION["api_key"] = "sk-ant-wrong"
    found = asyncio.run(claude_connection.status())
    assert found["online"] is False and found["key_works"] is False and "refused" in found["detail"]


# ---------------------------------------------------------------- the console's choice, switched while the studio runs

class Settings_table:
    """The settings table and users' roles, as claude_connection reads and writes them."""

    def __init__(self, roles=None):
        self.rows, self.roles = {}, roles or {}

    def setting(self, key, default=None):
        return self.rows.get(key, default)

    def set_setting(self, key, value):
        self.rows[key] = str(value)

    def one(self, sql, params):
        return {"role": self.roles[params[0]]} if params[0] in self.roles else None


def test_the_key_is_sealed_and_never_given_back():
    db, settings = Settings_table(), Settings()
    said = claude_connection.save(db, settings, {"mode": "api_key", "api_key": API_KEY})
    assert said == ["connection: Claude on this PC to Anthropic API key", "a new API key"]
    assert db.rows["anthropic_api_key"].startswith(vault.MARK) and API_KEY not in db.rows["anthropic_api_key"]
    shown = claude_connection.public(db, settings)
    assert API_KEY not in json.dumps(shown)
    assert shown == {"mode": "api_key", "modes": claude_connection.MODES, "has_api_key": True, "fixed": [], "testing": ""}
    assert claude_connection.save(db, settings, {"api_key": "  "}) == []   # blank: the key is kept
    assert claude.CONNECTION == {"mode": "api_key", "api_key": API_KEY}


def test_what_the_console_may_not_save():
    db, settings = Settings_table(), Settings()
    for body in ({"mode": "ollama"}, {"mode": "lufi_bridge"}):
        with pytest.raises(ValueError, match="Pick Claude on this PC or the Anthropic API key"):
            claude_connection.save(db, settings, body)
    assert db.rows == {}


def test_an_environment_variable_wins_and_the_console_cannot_change_it():
    db, settings = Settings_table(), Settings(claude_connection="api_key", anthropic_api_key="from-env")
    settings.from_environment = {"anthropic_api_key"}
    db.rows.update(anthropic_api_key=vault.seal("from-console"))
    found = claude_connection.current(db, settings)
    assert found["anthropic_api_key"] == "from-env" and found["fixed"] == ["anthropic_api_key"]
    assert found["claude_connection"] == "api_key"   # config.json's, as none was saved
    with pytest.raises(ValueError, match="SCENE_ANTHROPIC_API_KEY"):
        claude_connection.save(db, settings, {"api_key": "another"})


def test_config_reads_which_settings_the_environment_gave(monkeypatch, tmp_path):
    from scene.config import load_settings
    monkeypatch.setenv("SCENE_CLAUDE_CONNECTION", "api_key")
    monkeypatch.setenv("SCENE_ENV_FILE", str(tmp_path / "none.env"))
    found = load_settings(tmp_path / "none.json")
    assert found.claude_connection == "api_key" and "claude_connection" in found.from_environment
    assert "anthropic_api_key" not in found.from_environment
    monkeypatch.delenv("SCENE_CLAUDE_CONNECTION")
    assert load_settings(tmp_path / "none.json").claude_connection == "this_pc"   # the default: Claude on this PC


def test_an_unknown_mode_left_in_the_database_is_claude_on_this_pc():
    db = Settings_table()
    db.rows["claude_connection"] = "lufi_bridge"   # a database from before migration 0017, read without a registry
    assert claude_connection.current(db, Settings())["claude_connection"] == "this_pc"


# ---------------------------------------------------------------- the console's routes (the app, on the test database)

def test_the_console_card_switches_the_connection_and_never_shows_a_key(client, fake_claude):
    from test_api import console, register
    register(client)
    desk = console(client)
    shown = desk.put("/api/admin/claude-connection", json={"mode": "api_key", "api_key": API_KEY})
    assert shown.status_code == 200 and API_KEY not in shown.text
    body = shown.json()
    assert body["connection"]["mode"] == "api_key" and body["connection"]["has_api_key"] is True
    assert claude.CONNECTION == {"mode": "api_key", "api_key": API_KEY}   # in use at once, no restart
    assert API_KEY not in desk.get("/api/admin/claude-connection").text
    audit = desk.get("/api/admin/audit").json()["entries"][0]
    assert audit["action"] == "Changed the Claude connection" and API_KEY not in json.dumps(audit)
    assert desk.put("/api/admin/claude-connection", json={"mode": "nothing"}).status_code == 400
    desk.put("/api/admin/claude-connection", json={"mode": "this_pc"})
    assert claude.CONNECTION["mode"] == "this_pc" and client.get("/api/auth/state").json()["signup_open"] is True
    assert "signup_testing" not in desk.get("/api/admin/settings").json()
    desk.put("/api/admin/claude-connection", json={"mode": "api_key"})
    assert client.get("/api/auth/state").json()["signup_open"] is True   # the key was kept


def test_only_admins_see_the_claude_connection(client):
    from test_staff_roles import staff_member
    desk, _, _ = staff_member(client, "support")
    assert desk.get("/api/admin/claude-connection").status_code == 403
    assert desk.put("/api/admin/claude-connection", json={"mode": "api_key"}).status_code == 403

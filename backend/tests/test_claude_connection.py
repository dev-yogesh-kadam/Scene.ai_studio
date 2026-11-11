"""The Claude connection (claude.py's programs, claude_connection.py): the studio reaches Claude Code with an API key (the
`claude` here) or through the LUFI bridge, switched in the console with no restart.

Claude Code is a fake `claude` (fixtures/fake_claude.py), run by the studio itself or by a fake bridge (fake_bridge.py)
that follows the protocol of docs/servers.md and refuses anything the contract does not allow. Nothing here reaches
Anthropic, LUFI or this machine's own Claude Code."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from fake_bridge import FAKE_CLAUDE, FakeBridge, contract_problem
from scene import claude, claude_connection, vault
from scene.config import Settings
from scene.db import ACTING, EVERYONE

sdk = pytest.importorskip("claude_agent_sdk")

MESSAGES = [{"role": "system", "content": "You answer in JSON."}, {"role": "user", "content": "hi"}]
SCHEMA = {"type": "object", "properties": {"reply": {"type": "string"}}, "required": ["reply"]}
API_KEY, BRIDGE_KEY = "sk-ant-test-0123456789", "bridge-key"


@pytest.fixture(scope="module")
def bridge():
    found = FakeBridge(BRIDGE_KEY)
    yield found
    found.stop()


@pytest.fixture
def fake_claude(monkeypatch, tmp_path):
    """The fake `claude` in place of Claude Code here; returns the file its runs are written down in."""
    log = tmp_path / "runs.jsonl"
    monkeypatch.setattr(claude, "find", lambda: str(FAKE_CLAUDE))
    monkeypatch.setattr(claude, "RUN_WITH", (sys.executable,))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_SAY", raising=False)
    return log


@pytest.fixture(params=["api_key", "lufi_bridge"])
def connection(request, fake_claude, bridge):
    """Each test with it runs once with each connection: (mode, the fake bridge or None, the runs' file)."""
    bridge.refuse, bridge.starts[:] = None, []
    if request.param == "api_key":
        claude.CONNECTION = {"mode": "api_key", "api_key": API_KEY, "bridge_url": "", "bridge_key": ""}
        return SimpleNamespace(mode="api_key", bridge=None, log=fake_claude)
    claude.CONNECTION = {"mode": "lufi_bridge", "api_key": "", "bridge_url": bridge.url, "bridge_key": BRIDGE_KEY}
    return SimpleNamespace(mode="lufi_bridge", bridge=bridge, log=fake_claude)


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
    if connection.bridge:
        [start] = connection.bridge.starts
        assert start["env"] == {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"} and start["files"]["system_prompt"].startswith("You answer")
        assert start["args"][start["args"].index("--system-prompt-file") + 1] == "@system_prompt"
        assert API_KEY not in json.dumps(start) and BRIDGE_KEY not in json.dumps(start)   # never a key to LUFI
        assert run["cwd"] == connection.bridge.folder and run["api_key"] is None
    else:
        assert run["api_key"] == API_KEY and run["cwd"] != str(tmp_path / "home")   # a thrown-away folder of its own
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
    assert len(run["messages"]) == 2 and run["memory"] == "1"
    if connection.bridge:
        args = connection.bridge.starts[0]["args"]
        assert args[args.index("--allowedTools") + 1] == "mcp__studio__find_assets"   # the studio's tool: allowed by the contract
        assert not any(a.startswith("--") and "=" in a for a in args) and args[args.index("--setting-sources") + 1] == ""
        assert contract_problem(args, connection.bridge.starts[0]["env"]) is None


def test_compact_and_rename_go_on_stdin(connection, tmp_path):
    thread = {"key": "k", "id": "fake-session-1"}
    assert asyncio.run(claude.compact(service(tmp_path), thread)) == 9000
    [run] = runs(connection.log)
    assert run["messages"] == [{"role": "user", "content": "/compact"}] and "/compact" not in run["args"]
    assert run["args"][run["args"].index("--resume") + 1] == "fake-session-1"


def test_claude_codes_version_by_the_connection(connection):
    assert asyncio.run(claude_connection.version()) == "2.1.310"


# ---------------------------------------------------------------- the bridge's refusals, in the studio's words

@pytest.mark.parametrize("code, raised, words", [
    ("busy", claude.Busy, "as many calls as it takes"),
    ("not_signed_in", claude.Failed, "Claude on LUFI is signed out"),
    ("bad_key", claude.Failed, "The bridge key is wrong"),
    ("locked", claude.Failed, "The bridge key is wrong"),
    ("off", claude.Failed, "switched off"),
    ("timeout", claude.Failed, "longer than the bridge allows"),
    ("refused_flag", claude.Failed, "refused how the studio starts Claude Code"),
    ("internal", claude.Failed, "could not run Claude Code"),
])
def test_every_refusal_of_the_bridge_is_said_in_the_studios_words(connection, tmp_path, code, raised, words):
    if not connection.bridge:
        pytest.skip("the bridge's own")
    connection.bridge.refuse = code
    with pytest.raises(raised, match=words) as caught:
        asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    assert type(caught.value) is raised and claude.RUNNING["now"] == 0


def test_a_refusal_in_a_live_session_closes_its_program(connection, tmp_path):
    if not connection.bridge:
        pytest.skip("the bridge's own")
    from scene.agent import AgentBusy
    connection.bridge.refuse = "busy"
    thread = {"key": "k", "id": None}
    with pytest.raises(claude.Busy):
        asyncio.run(converse(service(tmp_path), "hi", thread))
    assert not claude.live and claude.RUNNING["now"] == 0 and issubclass(AgentBusy, Exception)


def test_a_wrong_key_and_a_bridge_that_is_not_there(bridge, tmp_path, fake_claude):
    claude.CONNECTION = {"mode": "lufi_bridge", "api_key": "", "bridge_url": bridge.url, "bridge_key": "not-the-key"}
    with pytest.raises(claude.Failed, match="The bridge key is wrong"):
        asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    found = asyncio.run(claude_connection.status())
    assert found["online"] is False and "bridge key is wrong" in found["detail"]
    claude.CONNECTION = dict(claude.CONNECTION, bridge_url="http://127.0.0.1:9", bridge_key=BRIDGE_KEY)
    with pytest.raises(claude.Failed, match="The LUFI bridge is not reachable"):
        asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    with pytest.raises(claude.Failed, match="not reachable"):
        claude.bridge_call("GET", "/health")


def test_signed_out_and_missing_claude_code(connection, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SAY", "signed_out")
    said = "Claude on LUFI is signed out" if connection.bridge else "not signed in: the Anthropic API key"
    with pytest.raises(claude.Failed, match=said):
        asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    if not connection.bridge:
        monkeypatch.setattr(claude, "find", lambda: "")
        with pytest.raises(claude.Failed, match="not installed with the studio"):
            asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))


def test_a_deleted_conversation_is_forgotten_on_lufi(bridge):
    claude.CONNECTION = {"mode": "lufi_bridge", "api_key": "", "bridge_url": bridge.url, "bridge_key": BRIDGE_KEY}
    claude.forget({"home": "unused"}, "0b6c1f0e-1111-2222-3333-444455556666")
    claude.forget({"home": "unused"}, "../not-a-session")   # never sent
    assert bridge.forgotten[-1] == "0b6c1f0e-1111-2222-3333-444455556666" and "../not-a-session" not in bridge.forgotten


def test_the_studio_keeps_to_the_contract():
    assert contract_problem(["-p", "--resume=abc"], {}) == "the argument '--resume=abc'"
    assert claude.split_flags(["--resume=abc", "--setting-sources=", "--model", "a=b"]) == ["--resume", "abc", "--setting-sources", "",
                                                                                          "--model", "a=b"]
    assert "positional" not in str(contract_problem(["-p", "/compact"], {})) and contract_problem(["-p", "/compact"], {})
    assert contract_problem(["--allowedTools", "mcp__other__x", "--mcp-config", '{"mcpServers": {"studio": {"type": "sdk"}}}'], {})
    assert contract_problem(["-p"], {"ANTHROPIC_API_KEY": "x"})
    sdk_config = ["--mcp-config", '{"mcpServers": {"studio": {"type": "sdk", "name": "studio"}}}']
    assert contract_problem(["--allowedTools", "mcp__studio__find_assets,WebSearch", *sdk_config], {}) is None
    assert contract_problem(["--allowedTools", "mcp__studio__*", *sdk_config], {})   # no wildcards
    assert contract_problem(["--tools", "WebSearch,Bash"], {})
    assert contract_problem(["--settings", '{"permissions": {}}'], {})


# ---------------------------------------------------------------- the connection's health

def test_the_bridges_health(bridge, fake_claude):
    claude.CONNECTION = {"mode": "lufi_bridge", "api_key": "", "bridge_url": bridge.url, "bridge_key": BRIDGE_KEY}
    found = asyncio.run(claude_connection.status(run_claude=True))
    assert found["online"] is True and found["signed_in"] is True and found["claude_version"] == "2.1.310"
    assert found["limit"] == 4 and found["testing"] == claude_connection.TESTING
    bridge.health["signed_in"] = False
    try:
        found = asyncio.run(claude_connection.status())
    finally:
        bridge.health["signed_in"] = True
    assert found["online"] is False and "signed out" in found["detail"]


def test_the_api_keys_health(fake_claude, monkeypatch):
    asked = []

    def answer(request):
        asked.append(request)
        return httpx.Response(200 if request.headers["x-api-key"] == API_KEY else 401, json={"data": []})
    real = httpx.AsyncClient
    monkeypatch.setattr(claude_connection.httpx, "AsyncClient", lambda **k: real(transport=httpx.MockTransport(answer), **k))
    claude.CONNECTION = {"mode": "api_key", "api_key": "", "bridge_url": "", "bridge_key": ""}
    assert "No Anthropic API key" in asyncio.run(claude_connection.status())["detail"] and not asked
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


def test_switching_takes_effect_on_the_next_call_with_no_restart(bridge, fake_claude, tmp_path):
    db, settings, s = Settings_table(), Settings(), service(tmp_path)
    bridge.starts[:] = []
    claude_connection.save(db, settings, {"mode": "api_key", "api_key": API_KEY})
    asyncio.run(claude.ask(s, "sonnet", MESSAGES, SCHEMA))
    assert runs(fake_claude)[-1]["api_key"] == API_KEY and not bridge.starts

    async def tab():
        thread = {"key": "1:tab1:3", "id": None}
        await converse(s, "hi", thread)
        claude_connection.save(db, settings, {"mode": "lufi_bridge", "bridge_url": bridge.url, "bridge_key": BRIDGE_KEY})
        await converse(s, "hi again", thread)   # the same tab: its session opened again, through the bridge
        await claude.close_all()
    asyncio.run(tab())
    assert len(bridge.starts) == 1 and bridge.starts[0]["args"][bridge.starts[0]["args"].index("--resume") + 1] == "fake-session-1"
    asyncio.run(claude.ask(s, "sonnet", MESSAGES, SCHEMA))
    assert len(bridge.starts) == 2
    claude_connection.save(db, settings, {"mode": "api_key"})   # back: the key it had is kept
    asyncio.run(claude.ask(s, "sonnet", MESSAGES, SCHEMA))
    assert len(bridge.starts) == 2 and runs(fake_claude)[-1]["api_key"] == API_KEY


def test_keys_are_sealed_and_never_given_back():
    db, settings = Settings_table(), Settings()
    said = claude_connection.save(db, settings, {"mode": "lufi_bridge", "bridge_url": "http://100.64.0.7:8765/", "bridge_key": BRIDGE_KEY,
                                                 "api_key": API_KEY})
    assert said == ["connection: Anthropic API key to LUFI bridge", "bridge address: http://100.64.0.7:8765", "a new bridge key",
                    "a new API key"]
    for key in ("claude_bridge_key", "anthropic_api_key"):
        assert db.rows[key].startswith(vault.MARK) and BRIDGE_KEY not in db.rows[key] and API_KEY not in db.rows[key]
    shown = claude_connection.public(db, settings)
    assert BRIDGE_KEY not in json.dumps(shown) and API_KEY not in json.dumps(shown)
    assert shown == {"mode": "lufi_bridge", "modes": claude_connection.MODES, "bridge_url": "http://100.64.0.7:8765",
                     "has_bridge_key": True, "has_api_key": True, "fixed": [], "testing": claude_connection.TESTING}
    assert claude_connection.save(db, settings, {"bridge_key": "", "api_key": "  "}) == []   # blank: the keys are kept
    assert claude.CONNECTION["bridge_key"] == BRIDGE_KEY and claude.CONNECTION["api_key"] == API_KEY


def test_what_the_console_may_not_save():
    db, settings = Settings_table(), Settings()
    for body, words in [({"mode": "ollama"}, "Pick"), ({"mode": "lufi_bridge"}, "needs its address and its key"),
                        ({"bridge_url": "100.64.0.7:8765"}, "scheme, host and port"),
                        ({"bridge_url": "http://user:pw@100.64.0.7:8765"}, "scheme, host and port"),
                        ({"bridge_url": "http://100.64.0.7:8765/run"}, "scheme, host and port")]:
        with pytest.raises(ValueError, match=words):
            claude_connection.save(db, settings, body)
    assert db.rows == {}


def test_an_environment_variable_wins_and_the_console_cannot_change_it():
    db, settings = Settings_table(), Settings(claude_connection="lufi_bridge", claude_bridge_url="http://10.0.0.1:1", claude_bridge_key="from-env")
    settings.from_environment = {"claude_bridge_key"}
    db.rows.update(claude_bridge_key=vault.seal("from-console"), claude_bridge_url="http://100.64.0.7:8765")
    found = claude_connection.current(db, settings)
    assert found["claude_bridge_key"] == "from-env" and found["claude_bridge_url"] == "http://100.64.0.7:8765"
    assert found["claude_connection"] == "lufi_bridge" and found["fixed"] == ["claude_bridge_key"]   # config.json's, as none was saved
    with pytest.raises(ValueError, match="SCENE_CLAUDE_BRIDGE_KEY"):
        claude_connection.save(db, settings, {"bridge_key": "another"})


def test_config_reads_which_settings_the_environment_gave(monkeypatch, tmp_path):
    from scene.config import load_settings
    monkeypatch.setenv("SCENE_CLAUDE_CONNECTION", "lufi_bridge")
    monkeypatch.setenv("SCENE_ENV_FILE", str(tmp_path / "none.env"))
    found = load_settings(tmp_path / "none.json")
    assert found.claude_connection == "lufi_bridge" and "claude_connection" in found.from_environment
    assert "claude_bridge_key" not in found.from_environment


# ---------------------------------------------------------------- testing on a personal subscription: the guard

def test_on_the_bridge_only_admins_reach_claude(bridge, fake_claude, tmp_path):
    db = Settings_table(roles={1: "admin", 2: "user", 3: "support"})
    guard = claude_connection.guard_for(db)

    async def as_(who):
        ACTING.set(who)
        await guard()
    claude.CONNECTION = {"mode": "lufi_bridge", "api_key": "", "bridge_url": bridge.url, "bridge_key": BRIDGE_KEY}
    asyncio.run(as_("1"))
    asyncio.run(as_(EVERYONE))   # the console, and the studio's own work
    for who in ("2", "3"):
        with pytest.raises(claude.Failed, match="only admins can use the agent"):
            asyncio.run(as_(who))
    claude.GUARD, bridge.starts[:] = guard, []

    async def user_asks():
        ACTING.set("2")
        return await claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA)
    with pytest.raises(claude.Failed, match="only admins"):
        asyncio.run(user_asks())
    assert not bridge.starts   # refused before anything reached LUFI
    claude.CONNECTION = {"mode": "api_key", "api_key": API_KEY, "bridge_url": "", "bridge_key": ""}
    asyncio.run(user_asks())   # the API key lifts it


def test_on_the_bridge_sign_up_is_closed_and_the_choice_kept():
    from scene.api.auth import signup_chosen, signup_open
    state = SimpleNamespace(db=Settings_table(), settings=Settings(allow_signup=True))
    assert signup_open(state) is True
    claude.CONNECTION = dict(claude.CONNECTION, mode="lufi_bridge")
    assert signup_open(state) is False and signup_chosen(state) is True
    claude.CONNECTION = dict(claude.CONNECTION, mode="api_key")
    assert signup_open(state) is True


# ---------------------------------------------------------------- the console's routes (the app, on the test database)

def test_the_console_card_switches_the_connection_and_never_shows_a_key(client, bridge, fake_claude):
    from test_api import console, register
    register(client)
    desk = console(client)
    shown = desk.put("/api/admin/claude-connection", json={"mode": "lufi_bridge", "bridge_url": bridge.url, "bridge_key": BRIDGE_KEY,
                                                           "api_key": API_KEY})
    assert shown.status_code == 200 and BRIDGE_KEY not in shown.text and API_KEY not in shown.text
    body = shown.json()
    assert body["connection"]["mode"] == "lufi_bridge" and body["connection"]["has_bridge_key"] is True
    assert body["status"]["online"] is True and body["status"]["testing"] == claude_connection.TESTING
    assert claude.CONNECTION["mode"] == "lufi_bridge"   # in use at once, no restart
    assert BRIDGE_KEY not in desk.get("/api/admin/claude-connection").text
    tested = desk.post("/api/admin/claude-connection/test").json()["test"]
    assert tested["online"] is True and tested["claude_version"] == "2.1.310"
    audit = desk.get("/api/admin/audit").json()["entries"][0]
    assert audit["action"] == "Changed the Claude connection" and BRIDGE_KEY not in json.dumps(audit) and API_KEY not in json.dumps(audit)
    assert client.get("/api/auth/state").json()["signup_open"] is False                     # testing: sign-up closed
    assert desk.get("/api/admin/settings").json()["signup_testing"] is True
    assert desk.put("/api/admin/claude-connection", json={"mode": "nothing"}).status_code == 400
    desk.put("/api/admin/claude-connection", json={"mode": "api_key"})
    assert client.get("/api/auth/state").json()["signup_open"] is True                      # lifted


def test_only_admins_see_the_claude_connection(client):
    from test_staff_roles import staff_member
    desk, _, _ = staff_member(client, "support")
    assert desk.get("/api/admin/claude-connection").status_code == 403
    assert desk.put("/api/admin/claude-connection", json={"mode": "api_key"}).status_code == 403

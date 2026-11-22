"""Claude on this PC (claude.LOCAL_SIGNIN, "this_pc"): the studio runs the `claude` signed in on this PC itself, with no
key, checked by claude_policy.py (its arguments, its environment and each line of its stdin), and the console's small
card of it (claude_connection.status: the sign-in, the plan's limits). Claude Code is the fake `claude`
(fixtures/fake_claude.py): nothing here reaches Anthropic or this machine's own Claude Code."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scene import claude, claude_connection, claude_policy, vault
from scene.config import Settings
from scene.db import ACTING, EVERYONE
from scene.providers import registry
from test_claude_connection import FAKE_CLAUDE, MESSAGES, SCHEMA, Settings_table, converse, runs, service

sdk = pytest.importorskip("claude_agent_sdk")

THIS_PC = {"mode": "this_pc", "api_key": ""}
LIMITS = {"status": "allowed", "unifiedWindows": {
    "five_hour": {"utilization": 0.27, "resetsAt": 4102444800, "status": "allowed"},
    "seven_day": {"utilization": 34, "resetsAt": 1000, "status": "allowed"}}}   # the week's reset has passed
GOOD = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--model", "sonnet",
        "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--max-turns", "3"]


@pytest.fixture
def here(monkeypatch, tmp_path):
    """The fake `claude` in place of this PC's, Claude on this PC in use, and an API key and a token in the studio's
    own environment (which must never reach claude). Returns the file its runs are written down in."""
    log = tmp_path / "runs.jsonl"
    monkeypatch.setattr(claude, "find", lambda: str(FAKE_CLAUDE))
    monkeypatch.setattr(claude, "RUN_WITH", (sys.executable,))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-in-the-studios-own-environment")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "a-token-in-the-studios-own-environment")
    for name in ("FAKE_CLAUDE_SAY", "FAKE_CLAUDE_AUTH", "FAKE_CLAUDE_LIMITS"):
        monkeypatch.delenv(name, raising=False)
    claude.CONNECTION = dict(THIS_PC)
    return log


# ---------------------------------------------------------------- the mode: the sign-in, never a key

def test_claude_on_this_pc_runs_with_no_key_even_one_in_the_studios_environment(here, tmp_path):
    answer, _, _ = asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    assert json.loads(answer) == {"reply": "hello"}
    [run] = runs(here)
    assert run["api_key"] is None and run["auth_token"] is None and run["memory"] == "1"


def test_the_api_key_connection_with_no_key_is_refused_not_run_on_the_sign_in(here, tmp_path):
    claude.CONNECTION = {"mode": "api_key", "api_key": ""}
    with pytest.raises(claude.Failed, match="Paste an Anthropic API key, or pick Claude on this PC"):
        asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    assert runs(here) == []   # nothing started
    claude.CONNECTION["api_key"] = "sk-ant-the-one-picked-0001"
    asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    assert runs(here)[-1]["api_key"] == "sk-ant-the-one-picked-0001" and runs(here)[-1]["auth_token"] is None


def test_a_live_session_calls_the_studios_own_tool_in_process(here, tmp_path):
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
    [run] = runs(here)
    assert Path(run["cwd"]).resolve() == (tmp_path / "home").resolve()   # the studio's fixed home, as with a key
    assert run["api_key"] is None and run["composed"] == [True, True] and "initialize" in run["controls"]
    assert claude.RUNNING["now"] == 0 and claude.RUNNING["answering"] == 0


def test_switching_between_the_modes_takes_effect_on_the_next_call(here, tmp_path):
    db, settings, s = Settings_table(), Settings(), service(tmp_path)

    async def tab():
        thread = {"key": "1:tab1:3", "id": None}
        await converse(s, "hi", thread)
        claude_connection.save(db, settings, {"mode": "api_key", "api_key": "sk-ant-picked-now-0002"})
        await converse(s, "hi again", thread)   # the same tab: its session opened again, with the key
        claude_connection.save(db, settings, {"mode": "this_pc"})
        await converse(s, "and back", thread)   # and again, on the sign-in
        await claude.close_all()
    asyncio.run(tab())
    assert [r["api_key"] for r in runs(here)] == [None, "sk-ant-picked-now-0002", None]
    assert all("--resume" in r["args"] or "--resume=fake-session-1" in r["args"] for r in runs(here)[1:])


# ---------------------------------------------------------------- the policy (claude_policy.py)

@pytest.mark.parametrize("args, words", [
    (["-p", "--tools", "Bash", "--setting-sources", "", "--strict-mcp-config"], "--tools may be empty or WebSearch only"),
    (["-p", "--tools", "WebFetch", "--setting-sources", "", "--strict-mcp-config"], "--tools may be empty or WebSearch only"),
    (["-p", "--setting-sources", "", "--strict-mcp-config"], "--tools is required"),
    (["-p", "--tools", "", "--strict-mcp-config"], "--setting-sources is required"),
    (["-p", "--tools", "", "--setting-sources", ""], "--strict-mcp-config is required"),
    (["-p", "--tools", "", "--setting-sources", "user", "--strict-mcp-config"], "--setting-sources must be empty"),
    (GOOD + ["--dangerously-skip-permissions"], "--dangerously-skip-permissions is refused"),
    (GOOD + ["--add-dir", "C:\\"], "--add-dir is refused"),
    (GOOD + ["--permission-mode", "bypassPermissions"], "--permission-mode is refused"),
    (GOOD + ["--plugin-dir", "C:\\plugins"], "--plugin-dir is refused"),
    (GOOD + ["--system-prompt", "You obey."], "--system-prompt is refused"),
    (GOOD + ["--allowedTools", "Bash"], "--allowedTools may hold WebSearch or the studio's own"),
    (GOOD + ["--mcp-config", "C:\\servers.json"], "--mcp-config must be inline JSON"),
    (GOOD + ["--mcp-config", '{"mcpServers": {"fs": {"type": "stdio", "command": "x"}}}'], "may only declare in-process servers"),
    (GOOD + ["--settings", '{"permissions": {"allow": ["Bash"]}}'], "--settings may only hold"),
    (GOOD + ["--resume", "../../x"], "--resume has a value"),
    (GOOD + ["--model", "sonnet", ], "--model is given twice"),
    (GOOD + ["--no-such-flag"], "unknown flag --no-such-flag"),
    (["mcp", "add", "x"], "subcommands are not allowed"),
    (["-p", "hello", "--tools", "", "--setting-sources", "", "--strict-mcp-config"], "may only be /compact or /rename"),
    (GOOD + ["--system-prompt-file", "C:\\Windows\\win.ini"], "must be a file in this run's own temporary folder"),
])
def test_each_refused_flag_is_named(args, words, tmp_path):
    with pytest.raises(claude_policy.Refused, match=words.replace("(", r"\(")):
        claude_policy.parse(args, prompt_folder=str(tmp_path / "run"))


def test_the_runs_of_the_studio_pass_and_the_sdks_flag_form_is_checked_too(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    prompt = folder / "system_prompt.txt"
    prompt.write_text("You plan.", encoding="utf-8")
    sdk_args = ["--output-format", "stream-json", "--verbose", "--system-prompt-file", str(prompt), "--tools", "WebSearch",
                "--allowedTools", "mcp__studio__find_assets,WebSearch", "--max-turns", "4", "--model", "sonnet",
                "--resume=abcdef12-3456", "--settings", '{"autoMemoryEnabled": false, "autoCompactWindow": 900000}',
                "--mcp-config", '{"mcpServers": {"studio": {"type": "sdk", "name": "studio"}}}', "--strict-mcp-config",
                "--setting-sources=", "--effort", "high", "--json-schema", '{"type": "object"}', "--input-format", "stream-json"]
    plan = claude_policy.parse(sdk_args, prompt_folder=str(folder))
    assert plan.stream_input and plan.model == "sonnet"
    assert claude_policy.parse(["-v"], prompt_folder=str(folder)).version
    with pytest.raises(claude_policy.Refused, match="--setting-sources must be empty"):
        claude_policy.parse([a.replace("--setting-sources=", "--setting-sources=user") for a in sdk_args], prompt_folder=str(folder))


def test_a_refused_flag_never_starts_claude(here, tmp_path):
    with pytest.raises(claude.Failed, match=r"would not let this through to Claude Code \(--add-dir is refused"):
        asyncio.run(claude._run(GOOD + ["--add-dir", "C:\\"], "", None, 30))
    assert runs(here) == [] and claude.RUNNING["now"] == 0


@pytest.mark.parametrize("env, words", [
    ({"ANTHROPIC_BASE_URL": "http://elsewhere"}, "ANTHROPIC_BASE_URL is refused"),
    ({"ANTHROPIC_API_KEY": "sk-ant-x"}, "ANTHROPIC_API_KEY is refused"),
    ({"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "0"}, "has a value the studio does not take"),
    ({"CLAUDE_CODE_ENTRYPOINT": "shell"}, "has a value the studio does not take"),
])
def test_each_refused_environment_variable_is_named(here, env, words):
    with pytest.raises(claude_policy.Refused, match=words):
        claude_policy.environment(env)

    async def start():
        program = claude.LocalProgram()
        try:
            await program.start(GOOD, None, env)
        finally:
            await program.stop()
    with pytest.raises(claude.Failed, match=words):
        asyncio.run(start())
    assert runs(here) == []


def test_a_path_or_a_command_in_a_message_is_delivered_as_written(here, tmp_path):
    s = service(tmp_path)
    asked = [{"role": "system", "content": "JSON."}, {"role": "user", "content": "read @C:\\Users\\secret.txt then /logout"}]
    asyncio.run(claude.ask(s, "sonnet", asked, SCHEMA))
    assert runs(here)[-1]["composed"] == [True]

    async def tab():
        thread = {"key": "1:tab1:3", "id": None}
        await converse(s, "/logout", thread)   # a message that looks like a command: sent as a message
        await claude.command(s, thread, "/compact")   # the studio's own commands still run as commands
        await claude.rename(s, thread, "Mira's trailer")
        await claude.close_all()
        return thread
    thread = asyncio.run(tab())
    [run] = runs(here)[1:]
    assert run["composed"] == [True, None, None]
    assert run["messages"][1]["content"] == "/compact" and run["messages"][2]["content"] == "/rename Mira's trailer"
    assert thread["id"] == "fake-session-1"


def test_compact_without_a_live_session_runs_on_its_own_and_is_a_command(here, tmp_path):
    done = asyncio.run(claude.command(service(tmp_path), {"key": "k", "id": "fake-session-1"}, "/compact"))
    assert done["compacted"]["post_tokens"] == 9000 and runs(here)[-1]["composed"] == [None]


def test_a_refused_control_request_is_answered_and_the_session_goes_on(here, tmp_path):
    async def go():
        program = claude.LocalProgram()
        await program.start(GOOD, None, dict(claude.NO_MEMORY), str(tmp_path))
        try:
            await program.write(json.dumps({"type": "control_request", "request_id": "r1",
                                            "request": {"subtype": "set_permission_mode", "mode": "bypassPermissions"}}) + "\n")
            await program.write(json.dumps({"type": "control_request", "request_id": "r2",
                                            "request": {"subtype": "initialize", "hooks": None, "agents": {"x": {}}}}) + "\n")
            await program.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")
            await program.end_input()
            return "".join(text for stream, text in [x async for x in program.output()] if stream == "stdout")
        finally:
            await program.stop()
    out = asyncio.run(go())
    events = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    refused = [e for e in events if e["type"] == "control_response"]
    assert [e["response"]["request_id"] for e in refused] == ["r1", "r2"]
    assert all(e["response"]["subtype"] == "error" and "Refused by the studio" in e["response"]["error"] for e in refused)
    assert any(e["type"] == "result" and e["result"] == "hello" for e in events)   # the session went on
    assert runs(here)[-1]["controls"] == []   # neither reached Claude Code


def test_a_line_that_stops_the_run(here):
    async def go(line):
        program = claude.LocalProgram()
        await program.start(GOOD)
        try:
            await program.write(line)
        finally:
            await program.stop()
    with pytest.raises(claude.Failed, match="a user message may hold text and base64 images only"):
        asyncio.run(go(json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "document"}]}}) + "\n"))
    with pytest.raises(claude.Failed, match="stdin line of type 'keep_alive' is refused"):
        asyncio.run(go(json.dumps({"type": "keep_alive"}) + "\n"))


# ---------------------------------------------------------------- status: the sign-in and the plan's limits

def test_signed_in_with_the_account_and_the_plan(here):
    found = asyncio.run(claude_connection.status())
    assert found["online"] is True and found["mode"] == "this_pc" and found["signed_in"] is True
    assert found["account"] == "owner@example.com" and found["plan"] == "pro" and found["claude_version"] == "2.1.310"
    assert found["testing"] == claude_connection.TESTING == "Personal Claude subscription"
    assert found["session"] is None and found["week"] is None   # no call has reported them yet
    assert found["running"] == 0 and found["limit"] == claude.PARALLEL


def test_auth_status_runs_without_the_studios_key(here):
    """With ANTHROPIC_API_KEY in its environment, Claude Code would answer about the key, not the account: the
    studio's own key (here) never reaches it, so the account is what it says."""
    said = asyncio.run(claude_connection.signin(fresh=True))
    assert said == {"signed_in": True, "account": "owner@example.com", "plan": "pro"}


def test_signed_out_says_the_fix(here, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", "signed_out")
    found = asyncio.run(claude_connection.status(run_claude=True))
    assert found["online"] is False and found["signed_in"] is False and found["account"] == ""
    assert found["detail"] == "Signed out. Press Sign in on Claude on this PC, in Servers & APIs → Providers."


def test_the_sign_in_is_kept_five_minutes_and_check_asks_again(here, monkeypatch):
    assert asyncio.run(claude_connection.status())["signed_in"] is True
    monkeypatch.setenv("FAKE_CLAUDE_AUTH", "signed_out")
    assert asyncio.run(claude_connection.status())["signed_in"] is True   # kept
    assert asyncio.run(claude_connection.status(run_claude=True))["signed_in"] is False   # Check: asked again


def test_claude_code_missing(here, monkeypatch):
    monkeypatch.setattr(claude, "find", lambda: "")
    found = asyncio.run(claude_connection.status())
    assert found["online"] is False and "not installed on this PC" in found["detail"]


def test_the_limits_once_a_call_reports_them_and_a_passed_reset_is_zero(here, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_LIMITS", json.dumps(LIMITS))
    kept = []
    claude.ON_LIMITS = kept.append
    asyncio.run(claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA))
    found = asyncio.run(claude_connection.status())
    assert found["session"] == {"utilization": 0.27, "resets_at": 4102444800}
    assert found["week"] == {"utilization": 0.0, "resets_at": None}   # reported as 34%, but its reset has passed
    assert kept and kept[-1]["five_hour"]["utilization"] == 0.27


def test_the_limits_are_kept_in_the_database_for_a_restart_and_other_processes(here):
    db = Settings_table()
    claude.ON_LIMITS = claude_connection.keep_limits(db)
    claude.note_limits({"rateLimitType": "five_hour", "utilization": 0.5, "resetsAt": 4102444800, "status": "allowed"})
    assert json.loads(db.rows[claude_connection.LIMITS_SETTING])["five_hour"]["utilization"] == 0.5
    claude.LIMITS.clear()   # a restart
    claude_connection.load_limits(db)
    assert claude.plan_windows()["session"] == {"utilization": 0.5, "resets_at": 4102444800}
    claude.LIMITS.clear()   # another process wrote them: status reads the database too
    found = asyncio.run(claude_connection.status(db=db))
    assert found["session"]["utilization"] == 0.5


# ---------------------------------------------------------------- the personal-use guard

def test_on_this_pcs_sign_in_every_user_reaches_claude_and_sign_up_is_as_chosen(here, tmp_path):
    from scene.api.auth import signup_open

    async def asks(who):
        ACTING.set(who)
        return await claude.ask(service(tmp_path), "sonnet", MESSAGES, SCHEMA)
    asyncio.run(asks("1"))
    asyncio.run(asks("2"))   # not an admin: no limit
    asyncio.run(asks(EVERYONE))
    assert len(runs(here)) == 3
    state = SimpleNamespace(db=Settings_table(), settings=Settings(allow_signup=True))
    assert claude_connection.testing() and signup_open(state) is True


# ---------------------------------------------------------------- the registry and the migration (the test database)

def migration(name):
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / name
    spec = importlib.util.spec_from_file_location("migration_" + name[:4], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migration(database, monkeypatch, name, step="upgrade"):
    module = migration(name)
    monkeypatch.setattr(module, "sql", lambda text: database.run(text))
    getattr(module, step)()


def to_newest(db, monkeypatch):
    """The test database back at the newest migration after a test replayed older ones: 0017 takes the bridge's kind
    away again, 0018 lets the tools on this PC be a provider (and adds On this PC)."""
    run_migration(db, monkeypatch, "0017_drop_claude_bridge.py")
    run_migration(db, monkeypatch, "0018_local_tools.py")


def replay_0016(db, monkeypatch):
    """0016 run again on a database at the newest migration: 0018 is undone first, as a downgrade past it would."""
    run_migration(db, monkeypatch, "0018_local_tools.py", "downgrade")
    run_migration(db, monkeypatch, "0016_claude_local.py")


def kinds(db):
    return [p["kind"] for p in registry.providers(db)]


def test_the_bridge_in_use_moves_to_claude_on_this_pc_then_leaves(database, monkeypatch):
    """A studio whose agent used the LUFI bridge, migrated the way it was: 0015 copies the bridge into the registry,
    0016 moves the agent to Claude on this PC, 0017 takes the bridge out with its keys. The test database is at the
    newest migration, so the bridge's kind is first allowed again (0017's downgrade), and put back as it was after."""
    db = database
    run_migration(db, monkeypatch, "0017_drop_claude_bridge.py", "downgrade")
    db.run("DELETE FROM providers")   # the downgrade's own bridge row: this one is made by 0015's copy
    try:
        for key, value in (("claude_connection", "lufi_bridge"), ("claude_bridge_url", "http://100.64.0.7:8765"),
                           ("claude_bridge_key", vault.seal("bridge-key-abcdef"))):
            db.set_setting(key, value)
        for statement in migration("0015_providers.py").COPY:
            db.run(statement)
        bridge = next(p for p in registry.providers(db) if p["kind"] == "claude_bridge")
        assert db.setting("agent_provider") == str(bridge["id"]) and registry.keys(db, bridge["id"])

        for _ in range(2):   # re-runnable
            run_migration(db, monkeypatch, "0016_claude_local.py")
        local = [p for p in registry.providers(db) if p["kind"] == "claude_local"]
        assert len(local) == 1 and local[0]["name"] == "Claude on this PC" and local[0]["legacy"] == "claude:local"
        assert db.setting("agent_provider") == str(local[0]["id"]) and db.setting("claude_connection") == "this_pc"
        assert registry.claude_values(db, Settings())["claude_connection"] == "this_pc"
        run_migration(db, monkeypatch, "0016_claude_local.py", "downgrade")
        assert db.setting("agent_provider") == str(bridge["id"]) and db.setting("claude_connection") == "lufi_bridge"
        assert "claude_local" not in kinds(db)
        run_migration(db, monkeypatch, "0016_claude_local.py")
        local = [p for p in registry.providers(db) if p["kind"] == "claude_local"]   # made again: a new id

        db.set_setting("agent_provider", str(bridge["id"]))   # as if it were picked again before 0017
        db.set_setting("claude_connection", "lufi_bridge")
        run_migration(db, monkeypatch, "0017_drop_claude_bridge.py")
        assert "claude_bridge" not in kinds(db) and "claude_local" in kinds(db)
        assert db.one("SELECT COUNT(*) AS n FROM provider_keys WHERE provider_id = ?", (bridge["id"],))["n"] == 0
        assert db.setting("agent_provider") == str(local[0]["id"]) and db.setting("claude_connection") == "this_pc"
        assert db.setting("claude_bridge_key") is None and db.setting("claude_bridge_url") is None
        with pytest.raises(Exception, match="providers_kind_known"):
            db.run("INSERT INTO providers (kind, name, base_url, active, priority, legacy) VALUES ('claude_bridge', 'x', '', 1, 1, '')")
        run_migration(db, monkeypatch, "0017_drop_claude_bridge.py", "downgrade")
        back = next(p for p in registry.providers(db) if p["kind"] == "claude_bridge")
        assert back["base_url"] == "" and registry.keys(db, back["id"]) == []   # no key is put back
        assert db.setting("agent_provider") == str(local[0]["id"])
    finally:
        to_newest(db, monkeypatch)   # the test database stays at the newest


def test_the_migration_keeps_an_anthropic_key_in_use_and_takes_one_without(database, monkeypatch):
    db = database
    for statement in migration("0015_providers.py").COPY:
        db.run(statement)   # a new database: Anthropic, with no key
    try:
        run_migration(db, monkeypatch, "0016_claude_local.py")
        local = next(p for p in registry.providers(db) if p["kind"] == "claude_local")
        anthropic = next(p for p in registry.providers(db) if p["kind"] == "anthropic")
        assert not db.setting("agent_provider")   # no one picked: the studio's start picks by config.json
        to_newest(db, monkeypatch)   # the studio starts at the newest migration
        registry.seed(db, Settings(claude_connection="api_key"))
        assert db.setting("agent_provider") == str(anthropic["id"])   # the test studios
        db.run("DELETE FROM settings WHERE key = 'agent_provider'")
        registry.seed(db, Settings())
        assert db.setting("agent_provider") == str(local["id"])   # the default of a new database

        db.set_setting("agent_provider", str(anthropic["id"]))
        db.set_setting("claude_connection", "api_key")   # picked in the console, with no key: refused, not moved
        replay_0016(db, monkeypatch)
        assert db.setting("agent_provider") == str(anthropic["id"])

        registry.add_key(db, anthropic["id"], "sk-ant-a-working-key-04", "API key", status="ok")
        db.set_setting("agent_provider", str(anthropic["id"]))
        replay_0016(db, monkeypatch)
        assert db.setting("agent_provider") == str(anthropic["id"])   # a key in use stays in use
    finally:
        to_newest(db, monkeypatch)   # 0016's check allows the bridge: the newest again


def test_claude_on_this_pc_takes_no_key_and_is_one(database):
    registry.seed(database, Settings())   # at start: Claude on this PC is always there, and the default
    local = next(p for p in registry.providers(database) if p["kind"] == "claude_local")
    assert registry.agent_provider_id(database) == local["id"]
    with pytest.raises(ValueError, match="has no key"):
        registry.add_key(database, local["id"], "anything-at-all-123", "Key")
    with pytest.raises(ValueError, match="is there already"):
        registry.add_provider(database, "claude_local")
    assert registry.capabilities_of("claude_local") == ["agent_llm"]


# ---------------------------------------------------------------- the console (the app, on the test database)

def test_the_console_picks_it_and_its_card_says_how_it_is(client, here):
    from test_api import console, register
    register(client)
    desk = console(client)
    claude.CONNECTION = dict(claude.CONNECTION, mode="api_key")   # the tests' studio starts on the API key (conftest)
    listed = desk.get("/api/admin/providers").json()
    local = next(p for p in listed["providers"] if p["kind"] == "claude_local")
    anthropic = next(p for p in listed["providers"] if p["kind"] == "anthropic")
    assert listed["keyless"] == ["claude_local"] and local["keys"] == [] and local["agent"] is False
    assert desk.post("/api/admin/providers/keys", json={"provider_id": local["id"], "secret": "x" * 12}).status_code == 400
    assert "Paste an Anthropic API key" in desk.post("/api/admin/claude-connection/test").json()["test"]["detail"]
    assert client.get("/api/auth/state").json()["signup_open"] is True
    picked = desk.put("/api/admin/providers/agent", json={"provider_id": local["id"]}).json()
    assert picked["testing"] == "Personal Claude subscription" and claude.CONNECTION["mode"] == "this_pc"
    assert client.get("/api/auth/state").json()["signup_open"] is True   # the admin's choice, on a personal subscription too
    shown = desk.get("/api/admin/claude-connection?fresh=1").json()["status"]
    assert shown["online"] is True and shown["account"] == "owner@example.com" and shown["plan"] == "pro"
    tested = desk.post("/api/admin/claude-connection/test").json()["test"]
    assert tested["online"] is True and tested["signed_in"] is True
    picked = desk.put("/api/admin/providers/agent", json={"provider_id": anthropic["id"]}).json()
    assert picked["testing"] == "" and claude.CONNECTION["mode"] == "api_key"
    assert client.get("/api/auth/state").json()["signup_open"] is True
    picks = [e for e in desk.get("/api/admin/audit").json()["entries"] if e["action"] == "Picked the agent's provider"]
    assert "Anthropic" in json.dumps(picks[0]) and "Claude on this PC" in json.dumps(picks[1])   # newest first


# ---------------------------------------------------------------- signing in and out from the console

@pytest.fixture
def signed_out(here, monkeypatch, tmp_path):
    """Claude Code here signed out, as `claude auth logout` leaves it; `auth login` and `auth logout` change it."""
    state = tmp_path / "auth.txt"
    state.write_text("signed_out", encoding="utf-8")
    monkeypatch.setenv("FAKE_CLAUDE_AUTH_FILE", str(state))
    claude_connection._signins.clear()
    return state


def test_sign_in_gives_the_link_and_the_code_signs_in(signed_out):
    async def go():
        started = await claude_connection.login_start()
        assert started["link"] == "https://claude.com/cai/oauth/authorize?code=true&client_id=fake&state=s1"
        assert claude_connection.login_waiting() == started
        return await claude_connection.login_code("  good-code#s1 ")
    said = asyncio.run(go())
    assert said == {"signed_in": True, "account": "owner@example.com", "plan": "pro"}
    assert signed_out.read_text() == "signed_in" and claude_connection.login_waiting() is None


def test_a_wrong_code_says_what_claude_code_said_and_stays_signed_out(signed_out):
    async def go():
        await claude_connection.login_start()
        await claude_connection.login_code("wrong-code#s1")
    with pytest.raises(claude.Failed, match=r"did not go through \(OAuth error: Request failed with status code 400\)"):
        asyncio.run(go())
    assert signed_out.read_text() == "signed_out" and claude_connection.login_waiting() is None


def test_a_code_with_nothing_waiting_or_that_cant_be_one(signed_out):
    with pytest.raises(claude.Failed, match="press Sign in again"):
        asyncio.run(claude_connection.login_code("good-code#s1"))
    with pytest.raises(ValueError, match="Paste the code"):
        asyncio.run(claude_connection.login_code("a b\nc"))


def test_cancel_stops_the_waiting_sign_in(signed_out):
    async def go():
        await claude_connection.login_start()
        process = claude_connection._login["process"]
        await claude_connection.login_cancel()
        return process.returncode
    assert asyncio.run(go()) is not None and claude_connection.login_waiting() is None


def test_sign_out(here, monkeypatch, tmp_path):
    state = tmp_path / "auth.txt"
    monkeypatch.setenv("FAKE_CLAUDE_AUTH_FILE", str(state))
    assert asyncio.run(claude_connection.signin(fresh=True))["signed_in"] is True
    said = asyncio.run(claude_connection.logout())
    assert said["signed_in"] is False and state.read_text() == "signed_out"


def test_the_console_signs_in_and_out(client, signed_out):
    from test_api import console, register
    register(client)
    desk = console(client)
    claude.CONNECTION = dict(THIS_PC)
    assert desk.get("/api/admin/claude-connection?fresh=1").json()["status"]["signed_in"] is False
    link = desk.post("/api/admin/claude-connection/signin").json()["link"]
    assert link.startswith("https://claude.com/cai/oauth/authorize")
    assert desk.post("/api/admin/claude-connection/signin/code", json={"code": "x y"}).status_code == 400
    shown = desk.post("/api/admin/claude-connection/signin/code", json={"code": "good-code#s1"}).json()["status"]
    assert shown["online"] is True and shown["account"] == "owner@example.com"
    assert desk.post("/api/admin/claude-connection/signin/code", json={"code": "good-code#s1"}).status_code == 409
    shown = desk.post("/api/admin/claude-connection/signout").json()["status"]
    assert shown["online"] is False and shown["signed_in"] is False
    actions = [e["action"] for e in desk.get("/api/admin/audit").json()["entries"]]
    assert {"Started signing Claude Code in", "Signed Claude Code in", "Signed Claude Code out"} <= set(actions)


def test_only_admins_sign_claude_code_in(client, signed_out):
    from test_staff_roles import staff_member
    claude.CONNECTION = {"mode": "api_key", "api_key": "sk-ant-test"}   # sign-up open, to make the staff member
    desk, _, _ = staff_member(client, "support")
    assert desk.post("/api/admin/claude-connection/signin").status_code == 403
    assert desk.post("/api/admin/claude-connection/signout").status_code == 403
    assert signed_out.read_text() == "signed_out"

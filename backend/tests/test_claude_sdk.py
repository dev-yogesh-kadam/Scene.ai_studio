"""The live session's contract with the Claude Agent SDK (claude.py). The SDK is faked only at its edge, the client
(ClaudeSDKClient: connect, query, receive_response, disconnect); everything else runs as it does in the studio: the
options claude.py builds, the studio's tools served by the SDK's own in-process MCP server (which checks each call
against the tool's schema before the tool runs), and the SDK's own message types. No Claude Code is started.

Most agent tests play Claude's session with one fake of claude.converse (conftest.chat_session); these are the tests
of converse itself, and of what Claude Code not answering means (claude.failure)."""

import asyncio
import json
import tempfile
import time
from pathlib import Path

import pytest

from scene import agent, agent_tools, claude, guardrails
from scene.agent import Agent, AgentBusy, AgentError, ContextLost

sdk = pytest.importorskip("claude_agent_sdk")
from mcp import types as mcp_types   # noqa: E402  (the SDK's own dependency)

REAL_CONVERSE = claude.converse   # the client fixture plays converse with a fake; a test here may put the real one back
PLAN = {"thought": "", "reply": "", "steps": [], "direction": "", "question": None}


class Call:
    """A step of a script: Claude Code calls a studio tool, through the SDK's MCP server, as the CLI would."""

    def __init__(self, name, args):
        self.name, self.args = name, args


class FakeSDKClient:
    """The SDK's client, at its edge. Each message sent is answered by the next script of `scripts`: SDK messages are
    yielded, a Call runs a tool through the real MCP server, an exception is raised mid-stream, and an async function
    is awaited (a hang, or a wait for a test's event)."""

    def __init__(self, options, made, scripts):
        self.options, self.scripts, self.sent, self.closed, self.results = options, scripts, [], False, []
        made.append(self)

    async def connect(self):
        pass

    async def query(self, text):
        self.sent.append(text)

    async def receive_response(self):
        for step in self.scripts.pop(0):
            if isinstance(step, Call):
                served = self.options.mcp_servers[claude.TOOLS_SERVER]["instance"]
                got = await served.get_request_handler("tools/call").handler(
                    None, mcp_types.CallToolRequestParams(name=step.name, arguments=step.args))
                error = bool(getattr(got, "is_error", getattr(got, "isError", False)))
                self.results.append((error, got.content[0].text))
                yield sdk.UserMessage(content=[sdk.ToolResultBlock(tool_use_id="t", content=got.content[0].text, is_error=error)])
            elif isinstance(step, BaseException):
                raise step
            elif callable(step):
                await step()
            else:
                yield step

    async def disconnect(self):
        self.closed = True


@pytest.fixture
def fake_sdk(monkeypatch):
    """Claude Code through the faked client: returns (the clients made, the scripts to answer with: append lists)."""
    made, scripts = [], []
    monkeypatch.setattr(sdk, "ClaudeSDKClient", lambda options, transport=None: FakeSDKClient(options, made, scripts))
    claude.live.clear()
    claude.held.clear()
    yield made, scripts
    claude.live.clear()
    claude.held.clear()


@pytest.fixture
def forgotten(monkeypatch):
    gone = []
    monkeypatch.setattr(claude, "forget", lambda s, session: gone.append(session))
    return gone


def brain(timeout=60):
    home = Path(tempfile.gettempdir()) / "scene-claude-sdk-tests"
    return Agent("", [{"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": ["sonnet", "opus"], "only": "",
                       "cli": "claude.exe", "timeout": timeout, "fast": "", "home": str(home), "window": 1_000_000}])


def init(session):
    return sdk.SystemMessage(subtype="init", data={"type": "system", "subtype": "init", "session_id": session})


def result(structured, session="s-1", subtype="success", text="", status=None, size=1000):
    return sdk.ResultMessage(subtype=subtype, duration_ms=0, duration_api_ms=0, is_error=subtype != "success" or bool(status),
                             num_turns=1, session_id=session, structured_output=structured, result=text, api_error_status=status,
                             usage={"input_tokens": 10, "cache_read_input_tokens": size - 10, "output_tokens": 5,
                                    "iterations": [{"input_tokens": 10, "cache_read_input_tokens": size - 10}]})


def said(text):
    return sdk.AssistantMessage(content=[sdk.TextBlock(text=text)], model="claude-sonnet")


def ask(b, message="go", tools=None, thread=None, **more):
    return b.ask_with_tools("You plan.", message, ["w"], tools or {}, model="claude/sonnet", thread=thread, **more)


# ---------------------------------------------------------------- what Claude Code is started with

def test_the_options_claude_code_is_started_with(fake_sdk):
    made, scripts = fake_sdk
    scripts.append([init("s-1"), result(dict(PLAN, reply="Hi."))])

    async def find_assets(call):
        return "nothing"
    b = brain()
    token = claude.EFFORT.set("high")
    try:
        asyncio.run(ask(b, tools={"find_assets": find_assets}, thread={"key": "1:tab1:0", "id": None}, web=True))
    finally:
        claude.EFFORT.reset(token)
    options = made[0].options
    assert options.cli_path == "claude" and options.model == "sonnet" and options.cwd == b.services["claude"]["home"]
    assert options.system_prompt["type"] == "file"
    system = Path(options.system_prompt["path"]).read_text(encoding="utf-8")
    assert system.startswith("You plan.") and "call them as you need" in system
    assert options.tools == list(claude.WEB_TOOLS) and set(options.allowed_tools) == {"mcp__studio__find_assets", *claude.WEB_TOOLS}
    assert options.strict_mcp_config is True and options.setting_sources == [] and options.resume is None
    assert options.max_turns == agent.TOOL_ROUNDS + 2 and options.effort == "high" and options.env == claude.NO_MEMORY
    assert options.output_format == {"type": "json_schema", "schema": agent.reply_format(["w"])}
    assert json.loads(options.settings)["autoMemoryEnabled"] is False


# ---------------------------------------------------------------- a stream of messages, tools called through the SDK

def test_a_stream_of_messages_is_one_answer_with_the_tools_it_called(fake_sdk):
    made, scripts = fake_sdk
    limits = {"status": "allowed_warning", "resetsAt": 1793183400, "utilization": 0.81}
    scripts.append([
        init("s-1"),
        sdk.AssistantMessage(content=[sdk.ThinkingBlock(thinking="Look her up.", signature=""),
                                      sdk.ToolUseBlock(id="t1", name="mcp__studio__find_assets", input={"query": "Mira"})],
                             model="claude-sonnet"),
        Call("find_assets", {"query": "Mira"}),
        said("Found her."),
        sdk.RateLimitEvent(rate_limit_info=sdk.RateLimitInfo(status="allowed_warning", resets_at=1793183400, raw=limits),
                           uuid="u1", session_id="s-1"),
        result(dict(PLAN, reply="Mira is item 7."), size=5000)])
    asked, story = [], []

    async def find_assets(call):
        asked.append(call)
        return "item 7: Mira"
    b = brain()
    thread = {"key": "1:tab1:0", "id": None, "record": lambda kind, text="", data=None: story.append(kind)}
    answer = asyncio.run(ask(b, tools={"find_assets": find_assets}, thread=thread))
    assert answer["reply"] == "Mira is item 7." and answer["tools"] == ["find_assets", "finish"]
    assert asked == [{"query": "Mira"}] and made[0].results == [(False, "item 7: Mira")]
    assert b.claude_limits == limits and answer["tokens"]["prompt"] == 5000
    assert thread["id"] == "s-1" and thread["size"] == 5000 and "opened" not in thread   # a tab's thread keeps no list
    assert story == ["thinking", "tool_call", "tool_result", "text"]


def test_a_call_that_does_not_fit_its_schema_is_answered_by_the_sdk_and_the_tool_never_runs(fake_sdk):
    made, scripts = fake_sdk
    scripts.append([Call("find_assets", {"op": "all"}), result(dict(PLAN, reply="Sorry."))])
    ran = []

    async def find_assets(call):
        ran.append(call)
        return "x"
    asyncio.run(ask(brain(), tools={"find_assets": find_assets}, thread={"key": "k", "id": None}))
    assert ran == [] and made[0].results[0][0] is True and "'query' is a required property" in made[0].results[0][1]


def test_an_old_sessions_film_ops_get_through_to_film_and_are_answered(fake_sdk):
    """A session begun when html and ffmpeg were ops of film still calls them so: the SDK lets the call through to the
    studio (no enum on op), which says what to call instead. An op film never had is answered the same way."""
    made, scripts = fake_sdk
    film = agent_tools.TOOLS["film"]
    calls = []

    async def film_tool(call):   # what api/workspace.film_op answers for an op it does not have
        calls.append(call)
        return agent.film_op_unknown(call["op"])
    scripts.append([Call("film", {"op": "html_page", "settings": {"width": 320}}), Call("film", {"op": "html", "settings": {}}),
                    result(dict(PLAN, reply="ok"))])
    asyncio.run(ask(brain(), tools={"film": film_tool}, thread={"key": "k", "id": None}))
    assert [c["op"] for c in calls] == ["html_page", "html"]
    error, text = made[0].results[0]
    assert not error and "render_html" in text and "ffmpeg tool" in text and "trim" in text
    assert "not one of" not in made[0].results[1][1]
    assert film[1]["properties"]["op"].get("enum") is None


def test_an_old_session_film_html_through_the_plan_endpoint_is_told_its_new_tool(client, fake_sdk):
    """The whole path with the real converse: the plan endpoint, the studio's tools, the SDK's MCP server."""
    from test_api import register
    made, scripts = fake_sdk
    claude.converse = REAL_CONVERSE   # the client fixture puts it back as it was when the test ends
    register(client)
    scripts.append([init("s-1"), Call("film", {"op": "html", "settings": {}}), Call("film", {"op": "page", "settings": {}}),
                    result(dict(PLAN, reply="Done.", claims_making=False, wants_sound=False, go_ahead=False))])
    plan = client.post("/api/agent/plan", json={"instruction": "make a title card", "run": "tab1"}).json()
    assert plan["reply"] == "Done.", plan
    (html_error, html_said), (unknown_error, unknown_said) = made[0].results
    assert not html_error and "film's html op is the render_html tool now" in html_said   # it ran (or said why not), and was told
    assert not unknown_error and unknown_said.startswith("film has no op \"page\"") and "render_html" in unknown_said


# ---------------------------------------------------------------- turns run out, compaction, errors mid-stream

def test_when_its_turns_run_out_it_is_asked_to_answer_and_both_turns_are_counted(fake_sdk):
    made, scripts = fake_sdk
    scripts += [[init("s-1"), result(None, subtype="error_max_turns", text="")], [result(dict(PLAN, reply="From what I have."))]]
    answer = asyncio.run(ask(brain(), thread={"key": "k", "id": None}))
    assert answer["reply"] == "From what I have." and made[0].sent[1] == agent.FINISH_NOW
    assert answer["tokens"]["prompt"] == 2000 and len(made) == 1


def test_a_compaction_in_the_middle_of_a_turn_is_told(fake_sdk):
    made, scripts = fake_sdk
    scripts.append([init("s-1"), sdk.SystemMessage(subtype="compact_boundary", data={
        "compact_metadata": {"trigger": "auto", "pre_tokens": 900_000, "post_tokens": 20_000}}), result(dict(PLAN, reply="Still here."))])
    story = []
    thread = {"key": "k", "id": "s-1", "compacted": 2, "record": lambda kind, text="", data=None: story.append((kind, data))}
    asyncio.run(ask(brain(), thread=thread))
    assert thread["compacted"] == 3 and story == [("compact", {"trigger": "auto", "pre_tokens": 900_000, "post_tokens": 20_000})]
    assert made[0].options.resume == "s-1"


@pytest.mark.parametrize("error, raised, words", [
    (Exception("API Error: 429 {\"type\":\"rate_limit_error\"}"), AgentBusy, "usage limit"),
    (sdk.ProcessError("Command failed", exit_code=1, stderr="Invalid API key · Please run /login"), AgentError, "not signed in"),
    (Exception("No conversation found with session ID: s-1"), ContextLost, "gone"),
    (RuntimeError("the pipe broke"), AgentError, "Claude Code stopped: the pipe broke"),
    (sdk.CLINotFoundError(cli_path="claude.exe"), AgentError, "not installed with the studio"),
])
def test_an_error_in_the_middle_of_the_stream_closes_the_program_and_says_what_it_means(fake_sdk, error, raised, words):
    made, scripts = fake_sdk
    scripts.append([init("s-1"), said("Working on it."), error])
    with pytest.raises(raised, match=words) as caught:
        asyncio.run(ask(brain(), thread={"key": "k", "id": "s-1"}))
    assert type(caught.value) is raised and made[0].closed and not claude.live


def test_an_assistant_messages_own_error_is_read_before_its_words(fake_sdk):
    made, scripts = fake_sdk
    refused = sdk.AssistantMessage(content=[sdk.TextBlock(text="Something went wrong.")], model="claude-sonnet", error="rate_limit")
    scripts.append([init("s-1"), refused, result(None, subtype="success", text="Something went wrong.", status=500)])
    with pytest.raises(AgentBusy):
        asyncio.run(ask(brain(), thread={"key": "k", "id": "s-1"}))
    scripts.append([sdk.AssistantMessage(content=[], model="claude-sonnet", error="authentication_failed"), result(None, text="x", status=500)])
    with pytest.raises(AgentError, match="not signed in"):
        asyncio.run(ask(brain(), thread={"key": "k", "id": "s-1"}))


def test_compact_now_in_a_live_session_says_when_claude_code_refuses(fake_sdk):
    made, scripts = fake_sdk
    scripts += [[init("s-1"), result(dict(PLAN, reply="a"))], [result(None, text="API Error: 529 Overloaded", status=529)]]
    b = brain()
    thread = {"key": "k", "id": None}
    asyncio.run(ask(b, thread=thread))
    with pytest.raises(claude.Busy):
        asyncio.run(claude.compact(b.services["claude"], thread))
    assert made[0].sent == ["go", "/compact"] and made[0].closed and not claude.live


# ---------------------------------------------------------------- a message outside a tab: its own session, always removed

def test_a_one_off_session_that_fails_is_closed_and_its_files_removed(fake_sdk, forgotten):
    made, scripts = fake_sdk
    scripts.append([init("s-7"), said("Let me look."), RuntimeError("the program stopped")])
    with pytest.raises(AgentError, match="the program stopped"):
        asyncio.run(ask(brain()))
    assert made[0].closed and not claude.live and forgotten == ["s-7"]


def test_a_one_off_session_refused_at_the_limit_is_removed_too(fake_sdk, forgotten):
    made, scripts = fake_sdk
    scripts.append([init("s-8"), result(None, session="s-8", text="Claude AI usage limit reached", status=429)])
    with pytest.raises(AgentBusy):
        asyncio.run(ask(brain()))
    assert made[0].closed and not claude.live and forgotten == ["s-8"]


def test_a_one_off_session_that_goes_quiet_times_out_and_is_removed(fake_sdk, forgotten, monkeypatch):
    made, scripts = fake_sdk
    monkeypatch.setattr(claude, "WATCH", 0.02)

    async def hang():
        await asyncio.sleep(30)
    scripts.append([init("s-9"), hang])
    started = time.monotonic()
    with pytest.raises(AgentError, match="said nothing for 1 s"):
        asyncio.run(ask(brain(timeout=1)))
    assert time.monotonic() - started < 10 and made[0].closed and not claude.live and forgotten == ["s-9"]


def test_a_slow_tool_is_not_taken_for_a_quiet_claude(fake_sdk, monkeypatch):
    made, scripts = fake_sdk
    monkeypatch.setattr(claude, "WATCH", 0.02)

    async def film(call):   # a film operation may take minutes: Claude Code waits for it, quietly
        await asyncio.sleep(1.5)
        return "made item 9"
    scripts.append([init("s-1"), Call("film", {"op": "trim", "settings": {}}), result(dict(PLAN, reply="Trimmed."))])
    answer = asyncio.run(ask(brain(timeout=1), tools={"film": film}, thread={"key": "k", "id": None}))
    assert answer["reply"] == "Trimmed." and made[0].results == [(False, "made item 9")]


def test_a_one_off_session_stopped_by_the_user_is_removed(fake_sdk, forgotten):
    made, scripts = fake_sdk

    async def hang():
        await asyncio.sleep(30)
    scripts.append([init("s-10"), hang])

    async def stop_it():
        task = asyncio.ensure_future(ask(brain()))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.05)   # the clean-up was shielded: it ends on its own
    asyncio.run(stop_it())
    assert made[0].closed and not claude.live and forgotten == ["s-10"]


def test_a_burst_of_one_off_messages_waits_its_turn_and_never_closes_a_tabs_session(fake_sdk, monkeypatch, forgotten):
    # every tab is one user's here, to fill the studio's LIVE: their own limit (guardrails, 3 by default) raised to all of it
    monkeypatch.setitem(guardrails._seen, "guard_sessions_per_user", claude.LIVE)
    made, scripts = fake_sdk
    b = brain()
    tabs = ["1:tab{}:0".format(n) for n in range(claude.LIVE)]
    for n, key in enumerate(tabs):
        scripts.append([init("tab-{}".format(n)), result(dict(PLAN, reply="ok"), session="tab-{}".format(n))])
    most, release = [0], None

    async def busy():   # a one-off message being answered: how many are open now, then wait for the test
        most[0] = max(most[0], sum(1 for k in claude.live if k.startswith(claude.ONEOFF)))
        await release.wait()

    async def burst():
        nonlocal release
        release = asyncio.Event()
        for key in tabs:
            await ask(b, thread={"key": key, "id": None})
        for n in range(5):
            scripts.append([init("one-{}".format(n)), busy, result(dict(PLAN, reply="one-off"), session="one-{}".format(n))])
        asked = [asyncio.ensure_future(ask(b, "a question from the phone")) for _ in range(5)]
        await asyncio.sleep(0.3)
        assert sum(1 for k in claude.live if k.startswith(claude.ONEOFF)) == claude.ONEOFF_LIVE   # the rest wait
        release.set()
        return await asyncio.gather(*asked)

    answers = asyncio.run(burst())
    assert [a["reply"] for a in answers] == ["one-off"] * 5 and most[0] <= claude.ONEOFF_LIVE
    assert sorted(claude.live) == sorted(tabs) and not any(c.closed for c in made[:claude.LIVE])   # every tab still running
    assert sorted(forgotten) == ["one-{}".format(n) for n in range(5)]


def test_a_tab_in_the_middle_of_a_message_is_never_closed_to_make_room(fake_sdk, monkeypatch):
    # every tab is one user's here, to fill the studio's LIVE: their own limit (guardrails, 3 by default) raised to all of it
    monkeypatch.setitem(guardrails._seen, "guard_sessions_per_user", claude.LIVE)
    made, scripts = fake_sdk
    b = brain()
    tabs = ["1:tab{}:0".format(n) for n in range(claude.LIVE)]
    for n, key in enumerate(tabs + ["1:new:0"]):
        scripts.append([result(dict(PLAN, reply="ok"), session="s-{}".format(n))])

    async def go():
        for key in tabs:
            await ask(b, thread={"key": key, "id": None})
        with claude.holding(tabs[0]):   # its message is between two rounds (a plan sent back to be fixed)
            await ask(b, thread={"key": "1:new:0", "id": None})
    asyncio.run(go())
    assert tabs[0] in claude.live and tabs[1] not in claude.live and made[1].closed and not made[0].closed


# ---------------------------------------------------------------- what Claude Code not answering means: one function

LIMITS = {"status": "rejected", "resetsAt": 1793183400}


@pytest.mark.parametrize("said, more, kind, words", [
    ("Claude AI usage limit reached|1793183400", {}, claude.Busy, "usage limit"),
    ("You're out of extra usage · resets 5pm", {}, claude.Busy, "usage limit"),
    ("API Error: 529 {\"type\":\"overloaded_error\"}", {}, claude.Busy, "usage limit"),
    ("Request failed with status code 429", {}, claude.Busy, "usage limit"),
    ("", {"limits": LIMITS}, claude.Busy, "until"),
    ("Something went wrong.", {"status": 429}, claude.Busy, "usage limit"),
    ("Something went wrong.", {"kind": "rate_limit"}, claude.Busy, "usage limit"),
    ("No conversation found with session ID: 0f1e", {}, claude.Lost, "gone"),
    ("Invalid API key · Please run /login", {}, claude.Failed, "not signed in"),
    ("OAuth token has expired. Please obtain a new token or refresh your existing token.", {}, claude.Failed, "not signed in"),
    ("Failed to authenticate. API Error: 401", {}, claude.Failed, "not signed in"),
    ("Something went wrong.", {"status": 401}, claude.Failed, "not signed in"),
    ("Something went wrong.", {"kind": "authentication_failed"}, claude.Failed, "not signed in"),
    ("Something went wrong.", {"kind": "billing_error"}, claude.Failed, "could not pay"),
    # anything else: a safe default that quotes it, never taken for a limit or a sign-in by a stray number or word
    ("Saved the catalog in /state; 14290 items", {}, claude.Failed, "Claude could not answer: Saved the catalog"),
    ("", {}, claude.Failed, "stopped without an answer"),
])
def test_each_thing_claude_code_says_when_it_does_not_answer_means_one_thing(said, more, kind, words):
    error = claude.failure(said, more.get("limits"), more.get("status"), more.get("kind"))
    assert type(error) is kind and words in str(error)


def test_the_default_message_is_the_callers_and_quotes_at_most_300_characters():
    error = claude.failure("x " * 400, default="Claude Code could not do /compact: {}")
    assert type(error) is claude.Failed and str(error).startswith("Claude Code could not do /compact: x x")
    assert len(str(error)) <= len("Claude Code could not do /compact: ") + 300


# ---------------------------------------------------------------- what the live loop writes down

def test_the_live_loops_calls_are_written_down_off_the_event_loop(fake_sdk):
    """Each call is a row and a gzipped file of its whole messages (traces.Recorder): written on the database's threads,
    as chat() does, never on the event loop (where the tests' loop guard refused it and the record was lost)."""
    import threading
    made, scripts = fake_sdk
    scripts += [[init("s-1"), result(dict(PLAN, reply="ok"))], [result(None, text="the program stopped", subtype="error_during_execution")]]
    written = []

    class Recorder:
        def record(self, purpose, model, asked, started, messages, answer_format, **found):
            written.append((purpose, threading.current_thread() is threading.main_thread(), "error" in found))
    b = brain()
    b.recorder = Recorder()
    thread = {"key": "k", "id": None}
    asyncio.run(ask(b, thread=thread))
    with pytest.raises(AgentError):
        asyncio.run(ask(b, thread=thread))
    assert written == [("plan", False, False), ("plan", False, True)]

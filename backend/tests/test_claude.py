"""Claude as a model of the agent, through Claude Code on this machine (claude.py). Claude Code is faked: each test says
what its run prints, and what it was started with is recorded."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from scene import claude
from scene.agent import Agent, AgentError


class Run:
    def __init__(self, stdout, stderr=""):
        self.stdout, self.stderr = stdout, stderr


def printed(*events):
    return "\n".join(json.dumps(e) for e in events)


ALLOWED = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1793183400}}


def answered(structured, usage=None):
    return {"type": "result", "subtype": "success", "is_error": False, "structured_output": structured,
            "result": json.dumps(structured), "usage": usage or {}}


def fake_claude(monkeypatch, *outputs):
    """Claude Code prints `outputs` in turn; returns the runs it was started for: {"args", "message", "system"}."""
    runs, left = [], list(outputs)

    def run(args, line, room, timeout):
        system = Path(args[args.index("--system-prompt-file") + 1]).read_text(encoding="utf-8")
        runs.append({"args": args, "message": json.loads(line)["message"], "system": system, "room": room})
        out = left.pop(0)
        return out if isinstance(out, Run) else Run(out)

    monkeypatch.setattr(claude, "_run", run)
    return runs


def brain_with_claude(models="sonnet, haiku", fast="haiku"):
    s = {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": [m.strip() for m in models.split(",")],
         "only": "", "cli": "claude.exe", "timeout": 60, "fast": fast,
         "home": str(Path(tempfile.gettempdir()) / "scene-claude-tests")}
    return Agent("http://127.0.0.1:9", "", [s])


def test_claude_is_offered_only_when_named_and_installed(monkeypatch):
    assert claude.service("") is None and claude.service("off") is None
    monkeypatch.setattr(claude, "find", lambda path="": "")
    assert claude.service("sonnet") is None                                         # Claude Code isn't on this machine
    monkeypatch.setattr(claude, "find", lambda path="": "C:/bin/claude.exe")
    s = claude.service("sonnet, opus ,haiku", fast="haiku")
    assert s["models"] == ["sonnet", "opus", "haiku"] and s["cli"] == "C:/bin/claude.exe" and s["key"] == ""
    brain = Agent("http://127.0.0.1:9", "", [s])                                     # no key, and still offered
    assert brain.hosted() == [{"id": "claude", "name": "Claude"}]
    assert asyncio.run(brain.models()) == ["claude/sonnet", "claude/opus", "claude/haiku"]   # Ollama is down
    assert brain.helper("claude/opus") == "claude/haiku" and brain.helper("qwen3.6:35b") == "qwen3.6:35b"


def test_claude_answers_in_the_agents_shape_with_its_own_tools_off(monkeypatch):
    brain = brain_with_claude()
    runs = fake_claude(monkeypatch, printed(ALLOWED, answered({"reply": "Hello.", "steps": []},
                                                              {"input_tokens": 10, "cache_read_input_tokens": 300, "output_tokens": 20})))
    answer = asyncio.run(brain.ask("You plan.", "hi", ["video/h3_all_in_one"], model="claude/sonnet"))
    assert answer["reply"] == "Hello." and answer["model"] == "claude/sonnet"
    assert answer["tokens"] == {"prompt": 310, "cached": 300, "answer": 20}
    args = runs[0]["args"]
    assert args[args.index("--model") + 1] == "sonnet" and args[args.index("--tools") + 1] == ""   # it only answers
    assert args[args.index("--setting-sources") + 1] == "" and "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert json.loads(args[args.index("--json-schema") + 1])["required"] == ["thought", "reply", "steps", "direction", "question"]
    assert runs[0]["system"].startswith("You plan.")
    assert runs[0]["message"]["content"][-1]["text"].endswith("hi")
    assert brain.claude_limits["status"] == "allowed"


def test_a_conversation_and_pictures_go_in_one_message():
    system, blocks = claude.prompt_of([{"role": "system", "content": "Rules."}, {"role": "user", "content": "Make a film."},
                                       {"role": "assistant", "content": '{"tool": "look"}'}, {"role": "user", "content": "Result of look: a cat"}])
    assert system == "Rules." and blocks[1:] == ["[user]\nMake a film.", '[assistant]\n{"tool": "look"}', "[user]\nResult of look: a cat"]
    assert claude.prompt_of([{"role": "user", "content": "hi"}]) == ("", ["hi"])


def test_claude_looks_at_pictures(monkeypatch):
    brain = brain_with_claude()
    runs = fake_claude(monkeypatch, printed(answered({"reply": "A red square."})))
    asyncio.run(brain.chat([{"role": "system", "content": "Look."}, {"role": "user", "content": "What is it?"}], {"type": "object"},
                           model="claude/sonnet", images=["AAAA"]))
    picture = runs[0]["message"]["content"][1]
    assert picture == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}


def test_at_its_usage_limit_a_local_model_answers_instead(monkeypatch):
    brain = brain_with_claude()
    fake_claude(monkeypatch, printed({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1793183400}},
                                     {"type": "result", "subtype": "success", "is_error": True, "result": "Claude usage limit reached"}))

    async def local(messages_model, *args, **kwargs):
        return '{"reply": "From here.", "steps": []}', {}

    async def local_models():
        brain.sizes = {"big:27b": 17, "small:9b": 6}
        return ["big:27b", "small:9b"]

    monkeypatch.setattr(brain, "_ask_local", local)
    monkeypatch.setattr(brain, "_local_models", local_models)
    answer = asyncio.run(brain.ask("You plan.", "hi", [], model="claude/sonnet"))
    assert answer["reply"] == "From here. (Claude was busy, so small:9b answered.)" and answer["model"] == "small:9b"


@pytest.mark.parametrize("out, said", [
    (Run("", "Invalid API key · Please run /login"), "not signed in"),
    (Run(printed({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": ""}), ""), "could not answer"),
])
def test_claude_says_what_went_wrong(monkeypatch, out, said):
    brain = brain_with_claude()
    fake_claude(monkeypatch, out)
    with pytest.raises(AgentError, match=said):
        asyncio.run(brain.ask("You plan.", "hi", [], model="claude/sonnet"))


def test_when_the_rounds_run_out_claude_still_answers(monkeypatch):
    brain = brain_with_claude()
    working = {"tool": "find_assets", "query": "Mira", "thought": "", "reply": "", "steps": [], "direction": "", "question": None}
    runs = fake_claude(monkeypatch, printed(answered(working)), printed(answered(working)),
                       printed(answered({"reply": "Mira is item 7.", "steps": []})))

    async def find_assets(call):
        return "item 7: Mira"

    answer = asyncio.run(brain.ask_with_tools("You plan.", "Who is in my book?", [], {"find_assets": find_assets},
                                              model="claude/sonnet", rounds=2))
    assert answer["reply"] == "Mira is item 7." and answer["tools"] == ["find_assets", "find_assets"]
    assert "Now give your answer to the user" in runs[-1]["message"]["content"][-1]["text"]


def test_with_claude_picked_claude_looks_at_the_pictures_too():
    from types import SimpleNamespace
    from scene.api.workspace import _looks
    state = SimpleNamespace(agent=brain_with_claude())
    assert _looks(state, {"model": "claude/sonnet"}) == {"describe": "claude/haiku", "review": "claude/sonnet"}
    assert _looks(state, {"model": "qwen3.6:35b"}) == {"describe": None, "review": None}   # local: the usual ones, as before
    assert _looks(state, {}) == {"describe": None, "review": None}


# ---------------------------------------------------------------- a conversation in one session (threads)

def session_answer(structured, session="s-1", size=20000):
    return dict(answered(structured, {"input_tokens": 50, "cache_read_input_tokens": size - 50, "output_tokens": 10,
                                      "iterations": [{"input_tokens": 50, "cache_read_input_tokens": size - 50}]}), session_id=session)


def test_a_thread_sends_only_what_is_new_and_goes_on_in_its_session(monkeypatch, tmp_path):
    monkeypatch.setattr(claude, "sdk", None)   # without the Agent SDK: Claude Code is run for each call
    brain = brain_with_claude()
    brain.services["claude"]["home"] = str(tmp_path / "sessions")
    working = {"tool": "find_assets", "query": "Mira", "thought": "", "reply": "", "steps": [], "direction": "", "question": None}
    runs = fake_claude(monkeypatch, printed(session_answer({"reply": "Hello.", "steps": []})),
                       printed(session_answer(working)), printed(session_answer({"reply": "Mira is item 7.", "steps": []}, size=70000)))
    thread = {"id": None}
    asyncio.run(brain.ask("You plan.", "FULL first message", [], model="claude/sonnet", thread=thread))
    first = runs[0]["args"]
    assert "--resume" not in first and "--no-session-persistence" not in first   # kept, to go on with
    assert runs[0]["room"] == str(tmp_path / "sessions") and thread["id"] == "s-1"

    async def find_assets(call):
        return "item 7: Mira"

    answer = asyncio.run(brain.ask_with_tools("You plan.", "Only the new message", [], {"find_assets": find_assets},
                                              model="claude/sonnet", thread=thread))
    assert answer["reply"] == "Mira is item 7."
    second, third = runs[1], runs[2]
    assert second["args"][second["args"].index("--resume") + 1] == "s-1"
    assert [b["text"] for b in second["message"]["content"]] == ["Only the new message"]           # not the first message again
    assert [b["text"] for b in third["message"]["content"]] == ["Result of find_assets:\nitem 7: Mira"]   # nor its own answer
    assert thread["size"] == 70000
    plain = fake_claude(monkeypatch, printed(answered({"reply": "On its own."})))
    asyncio.run(brain.ask("You plan.", "hi", [], model="claude/sonnet"))   # no thread: a call of its own, nothing kept
    assert "--no-session-persistence" in plain[0]["args"] and "--resume" not in plain[0]["args"]


def test_a_follow_up_has_only_the_parts_that_changed_and_never_the_history():
    from scene import agent
    parts = agent.question_parts("first", [{"id": "w"}], [], "w", history=[{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}],
                                 book=[{"name": "Mira"}], direction="night")
    seen = agent.fingerprints(parts)
    later = agent.question_parts("second", [{"id": "w"}], [], "w", history=[{"role": "user", "content": "first"}, {"role": "assistant", "content": "ok"}],
                                 book=[{"name": "Mira"}, {"name": "Leo"}], direction="night")
    said = agent.follow_up(later, seen)
    assert '"Leo"' in said and "Workflows:" not in said and "Conversation so far" not in said and "night" not in said
    assert said.endswith("The user's new message:\nsecond") and "Items attached to the new message" in said
    assert "as it was" in said and "workflows" in said.split("as it was")[0]
    assert agent.question("q", [{"id": "w"}], [], "w") == "\n\n".join(t for _, t in agent.question_parts("q", [{"id": "w"}], [], "w"))


def state_with_a_user(tmp_path):
    import time
    from types import SimpleNamespace
    from scene.db import Database
    db = Database(tmp_path / "scene.db")
    db.run("INSERT INTO users (id, email, name, password_hash, created) VALUES (1, 'a@b.c', 'A', '', ?)", (time.time(),))
    return SimpleNamespace(agent=brain_with_claude(), db=db)


def test_a_conversation_goes_on_in_its_thread_until_it_changes(tmp_path):
    from scene.api.workspace import _keep_thread, _thread
    state = state_with_a_user(tmp_path)
    user, body = {"id": 1}, {"run": "tab1", "history": []}
    first = _thread(state, user, 3, body, "claude/sonnet", "SYSTEM")
    assert first["id"] is None
    first.update(id="s-1", full="the whole first message")
    _keep_thread(state, user, 3, body, "claude/sonnet", first, "Hello.")
    went_on = {"run": "tab1", "history": [{"instruction": "hi", "reply": "Hello."}]}
    kept = _thread(state, user, 3, went_on, "claude/sonnet", "SYSTEM")
    assert kept["id"] == "s-1" and "full" not in kept                                                       # kept in the database
    assert _thread(state, user, 3, dict(went_on, run="tab2"), "claude/sonnet", "SYSTEM")["id"] is None   # another tab
    assert _thread(state, user, 4, went_on, "claude/sonnet", "SYSTEM")["id"] is None                        # another project
    assert _thread(state, user, 3, went_on, "claude/opus", "SYSTEM")["id"] is None                          # another model
    assert _thread(state, user, 3, {"run": "tab1", "history": []}, "claude/sonnet", "SYSTEM")["id"] is None  # a new chat
    assert _thread(state, user, 3, went_on, "claude/sonnet", "OTHER SYSTEM")["id"] is None                  # a long skill came
    _keep_thread(state, user, 3, body, "claude/sonnet", dict(first, size=claude.SESSION_TOKENS + 1), "Hello.")
    assert _thread(state, user, 3, went_on, "claude/sonnet", "SYSTEM")["id"] is None                        # grown too long
    _keep_thread(state, user, 3, body, "claude/sonnet", first, None)                                       # Ollama stood in
    assert _thread(state, user, 3, went_on, "claude/sonnet", "SYSTEM")["id"] is None
    assert _thread(state, user, 3, went_on, "qwen3.6:35b", "SYSTEM") is None                                 # local: no thread


def test_a_deleted_tab_lets_its_claude_sessions_go(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scene import runs
    from scene.api import workspace
    state = state_with_a_user(tmp_path)
    runs.keep_thread(state.db, 1, "tab1", 3, "claude/sonnet", {"id": "s-1"})
    runs.keep_thread(state.db, 1, "tab1", 3, "claude/opus", {"id": "s-2"})
    runs.keep_thread(state.db, 1, "tab2", 3, "claude/opus", {"id": "s-3"})
    forgotten = []
    monkeypatch.setattr(claude, "forget", lambda s, session: forgotten.append(session))
    monkeypatch.setattr(workspace, "_project_id", lambda *a: 3)
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    asyncio.run(workspace.delete_board("agent-tab1", request, 3, {"id": 1}))
    assert sorted(forgotten) == ["s-1", "s-2"]
    assert runs.threads_of(state.db, 1, "tab1") == [] and runs.threads_of(state.db, 1, "tab2") == [{"id": "s-3"}]


def test_forget_removes_the_session_file_claude_code_keeps(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    home = tmp_path / "Data" / "claude"
    import re
    kept = tmp_path / "config" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(home.resolve()))
    kept.mkdir(parents=True)
    (kept / "abcd-1234.jsonl").write_text("{}")
    (kept / "other-5678.jsonl").write_text("{}")
    claude.forget({"home": str(home)}, "abcd-1234")
    claude.forget({"home": str(home)}, "../other-5678")   # not a session id: nothing is touched
    assert sorted(p.name for p in kept.iterdir()) == ["other-5678.jsonl"]


def test_a_lost_session_and_a_busy_claude(monkeypatch):
    from scene.agent import ContextLost
    brain = brain_with_claude()
    fake_claude(monkeypatch, Run("No conversation found with session ID: s-9\n" + printed(
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": ""})))
    with pytest.raises(ContextLost):
        asyncio.run(brain.ask("You plan.", "new only", [], model="claude/sonnet", thread={"id": "s-9"}))

    # at the limit a local model stands in, and it is given the whole first message, not the follow-up
    fake_claude(monkeypatch, Run("", "Claude usage limit reached"))
    given = []

    async def local(model, messages, *args, **kwargs):
        given.append(messages[1]["content"])
        return '{"reply": "From here.", "steps": []}', {}

    async def local_models():
        brain.sizes = {"small:9b": 6}
        return ["small:9b"]

    monkeypatch.setattr(brain, "_ask_local", local)
    monkeypatch.setattr(brain, "_local_models", local_models)
    asyncio.run(brain.ask("You plan.", "new only", [], model="claude/sonnet", thread={"id": "s-1", "full": "THE WHOLE MESSAGE"}))
    assert given == ["THE WHOLE MESSAGE"]


# ---------------------------------------------------------------- live sessions (the Agent SDK, faked)

sdk = pytest.importorskip("claude_agent_sdk")


@pytest.fixture(autouse=True)
def no_live_sessions():
    claude.live.clear()
    yield
    claude.live.clear()


def result(structured, session="s-1", subtype="success", size=1000):
    return sdk.ResultMessage(subtype=subtype, duration_ms=0, duration_api_ms=0, is_error=subtype != "success", num_turns=1,
                             session_id=session, structured_output=structured,
                             usage={"input_tokens": 10, "cache_read_input_tokens": size - 10, "output_tokens": 5,
                                    "iterations": [{"input_tokens": 10, "cache_read_input_tokens": size - 10}]})


class FakeClient:
    """A live Claude Code: each message is answered by the next turn of the script, a list of ("tool", name, args),
    which calls the studio's tool as Claude Code would, and then a ResultMessage (or an exception, raised)."""

    def __init__(self, settings, turns):
        self.settings, self.turns, self.sent, self.closed, self.results = settings, turns, [], False, []

    async def query(self, text):
        self.sent.append(text)

    async def receive_response(self):
        for step in self.turns.pop(0):
            if isinstance(step, BaseException):
                raise step
            if isinstance(step, tuple):
                got = await self.settings["handlers"][step[1]](step[2])
                self.results.append(got["content"][0]["text"])
            else:
                yield step

    async def disconnect(self):
        self.closed = True


def fake_live(monkeypatch, *turns):
    """Claude Code kept running; returns the clients opened, in order."""
    opened, left = [], list(turns)

    async def open_(s, settings):
        opened.append(FakeClient(settings, left))
        return opened[-1]

    monkeypatch.setattr(claude, "_open", open_)
    return opened


PLAN = {"thought": "", "reply": "", "steps": [], "direction": "", "question": None}


def test_a_tab_keeps_its_claude_running_and_calls_the_studios_tools_as_its_own(monkeypatch):
    brain = brain_with_claude()
    opened = fake_live(monkeypatch,
                       [("tool", "find_assets", {"query": "Mira"}), result(dict(PLAN, reply="Mira is item 7."))],
                       [result(dict(PLAN, reply="She has red hair."))])
    found = []

    async def find_assets(call):
        found.append(call)
        return "item 7: Mira"

    thread = {"key": "1:tab1:3:claude/sonnet", "id": None}
    answer = asyncio.run(brain.ask_with_tools("You plan.", "FULL first message", ["w"], {"find_assets": find_assets},
                                              model="claude/sonnet", thread=thread))
    assert answer["reply"] == "Mira is item 7." and answer["tools"] == ["find_assets", "finish"]
    assert found == [{"query": "Mira"}] and opened[0].results == ["item 7: Mira"]
    settings = opened[0].settings
    assert settings["resume"] is None and settings["model"] == "sonnet" and list(settings["tools"]) == ["find_assets"]
    assert "call them as you need" in settings["system"] and "names a \"tool\"" not in settings["system"]
    assert thread["id"] == "s-1" and answer["tokens"]["prompt"] == 1000

    again = asyncio.run(brain.ask_with_tools("You plan.", "Only the new message", ["w"], {"find_assets": find_assets},
                                             model="claude/sonnet", thread=thread))
    assert again["reply"] == "She has red hair." and len(opened) == 1                    # the same program, still running
    assert opened[0].sent == ["FULL first message", "Only the new message"]


def test_a_live_session_is_opened_again_when_its_conversation_changes(monkeypatch):
    brain = brain_with_claude()
    opened = fake_live(monkeypatch, [result(dict(PLAN, reply="a"))], [result(dict(PLAN, reply="b"), session="s-2")],
                       [result(dict(PLAN, reply="c"), session="s-2")])
    thread = {"key": "1:tab1:3:claude/sonnet", "id": None}
    asyncio.run(brain.ask_with_tools("You plan.", "one", ["w"], {}, model="claude/sonnet", thread=thread))
    thread.update(id=None)   # a new chat in the tab
    asyncio.run(brain.ask_with_tools("You plan.", "two", ["w"], {}, model="claude/sonnet", thread=thread))
    assert opened[0].closed and opened[1].settings["resume"] is None
    asyncio.run(brain.ask_with_tools("A long skill.", "three", ["w"], {}, model="claude/sonnet", thread=thread))
    assert opened[1].closed and opened[2].settings["resume"] == "s-2"                      # another prompt: the same session


def test_a_plan_that_cannot_run_goes_back_in_the_same_session(monkeypatch):
    brain = brain_with_claude()
    opened = fake_live(monkeypatch, [result(dict(PLAN, reply="Plan", steps=[{"x": 1}]))],
                       [result(dict(PLAN, reply="Fixed", steps=[{"x": 2}]))])

    async def finishing(answer):
        return "Step 1 cannot run." if answer["steps"] == [{"x": 1}] else None

    answer = asyncio.run(brain.ask_with_tools("You plan.", "go", ["w"], {}, finishing, model="claude/sonnet",
                                              thread={"key": "k", "id": None}))
    assert answer["reply"] == "Fixed" and opened[0].sent == ["go", "Step 1 cannot run."]


def test_when_its_turns_run_out_claude_is_asked_to_answer(monkeypatch):
    brain = brain_with_claude()
    opened = fake_live(monkeypatch, [result(None, subtype="error_max_turns")], [result(dict(PLAN, reply="From what I have."))])
    answer = asyncio.run(brain.ask_with_tools("You plan.", "go", ["w"], {}, model="claude/sonnet", thread={"key": "k", "id": None}))
    assert answer["reply"] == "From what I have." and opened[0].sent[1].startswith("Now give your answer")
    assert answer["tokens"]["prompt"] == 2000


def test_stopping_a_reply_closes_the_program_and_keeps_the_session(monkeypatch):
    brain = brain_with_claude()
    opened = fake_live(monkeypatch, [asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(brain.ask_with_tools("You plan.", "go", ["w"], {}, model="claude/sonnet", thread={"key": "k", "id": "s-1"}))
    assert opened[0].closed and not claude.live


def test_a_busy_claude_in_a_live_session_hands_the_whole_message_to_a_local_model(monkeypatch):
    brain = brain_with_claude()
    busy = result(None)
    busy.is_error, busy.result, busy.api_error_status = True, "usage limit", 429
    opened = fake_live(monkeypatch, [busy])
    given = []

    async def local(model, messages, *args, **kwargs):
        given.append(messages[1]["content"])
        return json.dumps({"tool": "finish", "args": {}, **PLAN, "reply": "From here."}), {}

    async def local_models():
        brain.sizes = {"small:9b": 6}
        return ["small:9b"]

    async def pick(wanted=None):
        return wanted

    monkeypatch.setattr(brain, "_ask_local", local)
    monkeypatch.setattr(brain, "_local_models", local_models)
    monkeypatch.setattr(brain, "pick_model", pick)
    answer = asyncio.run(brain.ask_with_tools("You plan.", "new only", ["w"], {}, model="claude/sonnet",
                                              thread={"key": "k", "id": "s-1", "full": "THE WHOLE MESSAGE"}))
    assert opened[0].closed and given and given[0] == "THE WHOLE MESSAGE"
    assert answer["model"] == "small:9b" and "was busy" in answer["reply"]


def test_idle_sessions_are_closed_and_the_tools_run_in_their_messages_request(monkeypatch):
    import contextvars
    import time
    who = contextvars.ContextVar("who", default="nobody")
    brain = brain_with_claude()
    opened = fake_live(monkeypatch, [("tool", "find_assets", {"query": "x"}), result(dict(PLAN, reply="a"))],
                       [result(dict(PLAN, reply="b"), session="s-2")])
    seen = []

    async def find_assets(call):
        seen.append(who.get())
        return "nothing"

    async def message():
        who.set("user 1")
        return await brain.ask_with_tools("You plan.", "go", ["w"], {"find_assets": find_assets}, model="claude/sonnet",
                                          thread={"key": "k1", "id": None})

    asyncio.run(message())
    assert seen == ["user 1"]
    claude.live["k1"].used = time.monotonic() - claude.IDLE - 1
    asyncio.run(brain.ask_with_tools("You plan.", "go", ["w"], {}, model="claude/sonnet", thread={"key": "k2", "id": None}))
    assert opened[0].closed and list(claude.live) == ["k2"]

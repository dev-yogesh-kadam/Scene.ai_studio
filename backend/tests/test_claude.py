"""Claude as a model of the agent, through Claude Code (claude.py). Claude Code is faked at the run of it (_run): each
test says what its run prints, and what it was started with is recorded. The two connections themselves, with a fake
`claude`, are test_claude_connection.py's and test_claude_local.py's."""

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

    async def run(args, line, room, timeout, files=None, program=None):
        assert args[args.index("--system-prompt-file") + 1] == "@system_prompt"   # the prompt goes as a file's text
        runs.append({"args": args, "message": json.loads(line)["message"], "system": files["system_prompt"], "room": room})
        out = left.pop(0)
        return out if isinstance(out, Run) else Run(out)

    monkeypatch.setattr(claude, "_run", run)
    return runs


def brain_with_claude(models="sonnet, haiku", fast="haiku"):
    s = {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": [m.strip() for m in models.split(",")],
         "only": "", "cli": "claude.exe", "timeout": 60, "fast": fast,
         "home": str(Path(tempfile.gettempdir()) / "scene-claude-tests")}
    return Agent("", [s])


def test_claude_is_offered_when_named_whichever_way_it_is_reached():
    assert claude.service("") is None and claude.service("off") is None
    # whether Claude Code can be reached is asked at each call (the connection may be switched): it is offered anyway
    s = claude.service("sonnet, opus ,haiku", fast="haiku")
    assert s["models"] == ["sonnet", "opus", "haiku"] and s["cli"] == "claude" and s["key"] == ""
    brain = Agent("", [s])                                                          # no key, and still offered
    assert asyncio.run(brain.models()) == ["claude/sonnet", "claude/opus", "claude/haiku"]
    assert brain.helper("claude/opus") == "claude/haiku" and brain.helper(None) == "claude/haiku"
    with pytest.raises(AgentError, match="claude_models"):
        asyncio.run(Agent("", []).models())                                         # no Claude: no model at all


def test_claude_answers_in_the_agents_shape_with_its_own_tools_off(monkeypatch):
    brain = brain_with_claude()
    runs = fake_claude(monkeypatch, printed(ALLOWED, answered({"reply": "Hello.", "steps": []},
                                                              {"input_tokens": 10, "cache_read_input_tokens": 300, "output_tokens": 20})))
    answer = asyncio.run(brain.ask("You plan.", "hi", ["video/h3_all_in_one"], model="claude/sonnet"))
    assert answer["reply"] == "Hello." and answer["model"] == "claude/sonnet"
    assert answer["tokens"] == {"prompt": 310, "cached": 300, "written": 0, "answer": 20}
    args = runs[0]["args"]
    assert args[args.index("--model") + 1] == "sonnet" and args[args.index("--tools") + 1] == ""   # it only answers
    assert args[args.index("--setting-sources") + 1] == "" and "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert json.loads(args[args.index("--json-schema") + 1])["required"] == ["thought", "concept", "reply", "steps", "direction", "question",
                                                                             "claims_making", "wants_sound", "go_ahead"]
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


def test_at_its_usage_limit_the_user_is_told(monkeypatch):
    from scene.agent import AgentBusy
    brain = brain_with_claude()
    fake_claude(monkeypatch, printed({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1793183400}},
                                     {"type": "result", "subtype": "success", "is_error": True, "result": "Claude usage limit reached"}))
    with pytest.raises(AgentBusy):
        asyncio.run(brain.ask("You plan.", "hi", [], model="claude/sonnet"))


@pytest.mark.parametrize("out, said", [
    (Run("", "Invalid API key · Please run /login"), "not signed in"),
    (Run(printed({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": ""}), ""), "could not answer"),
])
def test_claude_says_what_went_wrong(monkeypatch, out, said):
    brain = brain_with_claude()
    fake_claude(monkeypatch, out)
    with pytest.raises(AgentError, match=said):
        asyncio.run(brain.ask("You plan.", "hi", [], model="claude/sonnet"))


def test_a_message_with_no_tab_runs_in_a_session_of_its_own_that_is_then_forgotten(monkeypatch):
    brain = brain_with_claude()
    opened = fake_live(monkeypatch, [("tool", "find_assets", {"query": "Mira"}), result(dict(PLAN, reply="Mira is item 7."), session="s-5")])
    forgotten = []
    monkeypatch.setattr(claude, "forget", lambda s, session: forgotten.append(session))

    async def find_assets(call):
        return "item 7: Mira"

    answer = asyncio.run(brain.ask_with_tools("You plan.", "Who is in my book?", [], {"find_assets": find_assets},
                                              model="claude/sonnet"))
    assert answer["reply"] == "Mira is item 7." and answer["tools"] == ["find_assets", "finish"]
    assert opened[0].settings["resume"] is None and opened[0].results == ["item 7: Mira"]
    assert opened[0].closed and not claude.live and forgotten == ["s-5"]   # closed at once, and its file removed


def test_claude_is_not_offered_without_the_agent_sdk(monkeypatch):
    monkeypatch.setattr(claude, "sdk", None)
    with pytest.raises(RuntimeError, match="pip install claude-agent-sdk"):
        claude.service("sonnet")
    assert claude.service("off") is None   # Claude switched off: nothing to refuse


def test_with_claude_picked_claude_looks_at_the_pictures_too():
    from types import SimpleNamespace
    from scene.api.workspace import _looks
    state = SimpleNamespace(agent=brain_with_claude())
    assert _looks(state, {"model": "claude/sonnet"}) == {"describe": "claude/haiku", "review": "claude/sonnet"}
    assert _looks(state, {}) == {"describe": None, "review": None}


# ---------------------------------------------------------------- a conversation in one session (threads)

def session_answer(structured, session="s-1", size=20000):
    return dict(answered(structured, {"input_tokens": 50, "cache_read_input_tokens": size - 50, "output_tokens": 10,
                                      "iterations": [{"input_tokens": 50, "cache_read_input_tokens": size - 50}]}), session_id=session)


def test_a_thread_sends_only_what_is_new_and_goes_on_in_its_session(monkeypatch, tmp_path):
    brain = brain_with_claude()
    brain.services["claude"]["home"] = str(tmp_path / "sessions")
    runs = fake_claude(monkeypatch, printed(session_answer({"reply": "Hello.", "steps": []})),
                       printed(session_answer({"reply": "Mira is item 7.", "steps": []}, size=70000)))
    thread = {"id": None}
    asyncio.run(brain.ask("You plan.", "FULL first message", [], model="claude/sonnet", thread=thread))
    first = runs[0]["args"]
    assert "--resume" not in first and "--no-session-persistence" not in first   # kept, to go on with
    assert runs[0]["room"] == str(tmp_path / "sessions") and thread["id"] == "s-1"
    answer = asyncio.run(brain.ask("You plan.", "Only the new message", [], model="claude/sonnet", thread=thread,
                                   history=[{"role": "user", "content": "FULL first message"}, {"role": "assistant", "content": "Hello."}]))
    assert answer["reply"] == "Mira is item 7."
    second = runs[1]
    assert second["args"][second["args"].index("--resume") + 1] == "s-1"
    assert [b["text"] for b in second["message"]["content"]] == ["Only the new message"]           # not the first message again
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
    from conftest import POSTGRES, empty_postgres
    from scene.db import Database
    empty_postgres()
    db = Database(POSTGRES)
    db.run("INSERT INTO users (id, email, name, password_hash, created) VALUES (1, 'a@b.c', 'A', '', ?)", (time.time(),))
    for project in (3, 4):   # the projects its tabs are open in (claude_sessions.project_id is a key, migration 0007)
        db.run("INSERT INTO projects (id, user_id, name, created) VALUES (?, 1, ?, ?)", (project, "P{}".format(project), time.time()))
    return SimpleNamespace(agent=brain_with_claude(), db=db)


def test_a_tab_goes_on_in_one_session_whatever_the_claude_model(tmp_path):
    from scene.api.workspace import _keep_thread, _thread
    state = state_with_a_user(tmp_path)
    user, body = {"id": 1}, {"run": "tab1", "history": []}
    first = _thread(state, user, 3, body, "claude/sonnet", "SYSTEM")
    assert first["id"] is None
    first.update(id="s-1", full="the whole first message", size=900_000)
    _keep_thread(state, user, 3, body, "claude/sonnet", first, "Hello.")
    went_on = {"run": "tab1", "history": [{"instruction": "hi", "reply": "Hello."}]}
    kept = _thread(state, user, 3, went_on, "claude/sonnet", "SYSTEM")
    assert kept["id"] == "s-1" and "full" not in kept and kept["missed"] == []                             # kept in the database
    assert _thread(state, user, 3, dict(went_on, run="tab2"), "claude/sonnet", "SYSTEM")["id"] is None   # another tab
    assert _thread(state, user, 4, went_on, "claude/sonnet", "SYSTEM")["id"] is None                        # another project
    assert _thread(state, user, 3, went_on, "claude/opus", "SYSTEM")["id"] == "s-1"                         # another Claude model
    assert _thread(state, user, 3, went_on, "claude/sonnet", "OTHER SYSTEM")["id"] == "s-1"                 # a long skill came
    assert _thread(state, user, 3, went_on, "claude/sonnet", "SYSTEM")["size"] == 900_000                   # long: compacted, not let go
    assert _thread(state, user, 3, {"run": "tab1", "history": []}, "claude/sonnet", "SYSTEM")["id"] is None  # a new chat
    assert _thread(state, user, 3, went_on, "qwen3.6:35b", "SYSTEM") is None                                 # local: no thread

    # Gemini answered two turns in between: the session goes on, and they are sent along with the next message
    later = {"run": "tab1", "history": [{"instruction": "hi", "reply": "Hello."}, {"instruction": "a", "reply": "A by Gemini"},
                                        {"instruction": "b", "reply": "B by Gemini"}]}
    back = _thread(state, user, 3, later, "claude/sonnet", "SYSTEM")
    assert back["id"] == "s-1" and [t["reply"] for t in back["missed"]] == ["A by Gemini", "B by Gemini"]
    _keep_thread(state, user, 3, later, "claude/sonnet", dict(back, stood_in=True), "another model stood in")   # not Claude's answer
    assert _thread(state, user, 3, later, "claude/sonnet", "SYSTEM")["id"] == "s-1"                          # the thread stays as it was


def test_missed_turns_are_told_to_the_session():
    from scene.api.workspace import _missed_text
    said = _missed_text([{"instruction": "make it blue", "reply": "Made it blue."}])
    assert "another model answered" in said and "[user] make it blue" in said and "[assistant] Made it blue." in said
    assert _missed_text([]) == ""


def test_threads_from_before_one_per_model_are_taken_up(tmp_path):
    from scene import runs
    state = state_with_a_user(tmp_path)
    runs.write(state.db, 1, "tab1", "/claude/p3-claude.sonnet", {"id": "old", "last": "x"}, "studio", trusted=True)
    assert runs.kept_thread(state.db, 1, "tab1", 3)["id"] == "old"
    runs.keep_thread(state.db, 1, "tab1", 3, {"id": "new"})
    assert runs.kept_thread(state.db, 1, "tab1", 3)["id"] == "new"


def test_a_deleted_tab_lets_its_claude_sessions_go_and_keeps_their_story(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scene import runs, sessions
    from scene.api import workspace
    state = state_with_a_user(tmp_path)
    runs.keep_thread(state.db, 1, "tab1", 3, {"id": "s-1"})
    runs.write(state.db, 1, "tab1", "/claude/p4-claude.opus", {"id": "s-2"}, "studio", trusted=True)
    runs.keep_thread(state.db, 1, "tab2", 3, {"id": "s-3"})
    row = sessions.open_row(state.db, 1, 3, "tab1", "claude/sonnet", 1_000_000)
    sessions.record(state.db, row["id"], "user", "hello")
    forgotten = []
    monkeypatch.setattr(claude, "forget", lambda s, session: forgotten.append(session))
    monkeypatch.setattr(workspace, "_project_id", lambda *a: 3)
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    asyncio.run(workspace.delete_board("agent-tab1", request, 3, {"id": 1}))
    assert sorted(forgotten) == ["s-1", "s-2"]
    assert runs.threads_of(state.db, 1, "tab1") == [] and runs.threads_of(state.db, 1, "tab2") == [{"id": "s-3"}]
    assert sessions.one(state.db, row["ref"])["status"] == "deleted"
    assert [e["kind"] for e in sessions.events(state.db, row["id"])] == ["user", "note"]   # kept for good


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


def test_a_busy_claude_in_a_live_session_is_said_and_its_program_closed(monkeypatch):
    from scene.agent import AgentBusy
    brain = brain_with_claude()
    busy = result(None)
    busy.is_error, busy.result, busy.api_error_status = True, "usage limit", 429
    opened = fake_live(monkeypatch, [busy])
    with pytest.raises(AgentBusy):
        asyncio.run(brain.ask_with_tools("You plan.", "new only", ["w"], {}, model="claude/sonnet",
                                         thread={"key": "k", "id": "s-1", "full": "THE WHOLE MESSAGE"}))
    assert opened[0].closed


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


# ---------------------------------------------------------------- the story of a session, compacting, settings

def test_studio_sessions_have_memory_off_and_compact_at_ninety_percent(monkeypatch):
    s = {"window": 1_000_000}
    assert json.loads(claude.session_settings(s)) == {"autoMemoryEnabled": False, "autoCompactWindow": 900_000}
    assert json.loads(claude.session_settings({"window": 200_000}))["autoCompactWindow"] == 180_000
    runs = fake_claude(monkeypatch, printed(answered({"reply": "hi"})))
    asyncio.run(brain_with_claude().ask("You plan.", "hi", [], model="claude/sonnet"))
    args = runs[0]["args"]
    assert json.loads(args[args.index("--settings") + 1])["autoMemoryEnabled"] is False
    assert claude.NO_MEMORY == {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}


def test_what_claude_does_in_a_live_session_is_told_to_its_story(monkeypatch):
    brain = brain_with_claude()
    thinking = sdk.AssistantMessage(content=[sdk.ThinkingBlock(thinking="Look her up.", signature=""),
                                             sdk.ToolUseBlock(id="t1", name="mcp__studio__find_assets", input={"query": "Mira"})],
                                    model="claude-sonnet")
    tool_result = sdk.UserMessage(content=[sdk.ToolResultBlock(tool_use_id="t1", content=[{"type": "text", "text": "item 7"}])])
    compacted = sdk.SystemMessage(subtype="compact_boundary", data={"compact_metadata": {"trigger": "auto", "pre_tokens": 900_000,
                                                                                          "post_tokens": 20_000}})
    said = sdk.AssistantMessage(content=[sdk.TextBlock(text="Found her.")], model="claude-sonnet")
    fake_live(monkeypatch, [thinking, tool_result, compacted, said, result(dict(PLAN, reply="Mira is item 7."))])
    story = []
    thread = {"key": "k", "id": None, "record": lambda kind, text="", data=None: story.append((kind, text, data))}
    asyncio.run(brain.ask_with_tools("You plan.", "who is Mira", ["w"], {}, model="claude/sonnet", thread=thread))
    assert [k for k, _, _ in story] == ["thinking", "tool_call", "tool_result", "compact", "text"]
    assert story[1][1] == "find_assets" and story[1][2]["input"] == {"query": "Mira"} and story[2][1] == "item 7"
    assert story[3][2]["post_tokens"] == 20_000 and thread["compacted"] == 1


def test_compact_now_goes_on_in_the_same_session(monkeypatch):
    # its program is running: /compact goes to it
    opened = fake_live(monkeypatch, [result(dict(PLAN, reply="a"))],
                       [sdk.SystemMessage(subtype="compact_boundary", data={"compact_metadata": {"trigger": "manual", "pre_tokens": 850_000,
                                                                                                   "post_tokens": 12_000}}),
                        result(None)])
    brain = brain_with_claude()
    thread = {"key": "k", "id": None}
    asyncio.run(brain.ask_with_tools("You plan.", "go", ["w"], {}, model="claude/sonnet", thread=thread))
    s = brain.services["claude"]
    assert asyncio.run(claude.compact(s, thread)) == 12_000
    assert opened[0].sent == ["go", "/compact"] and len(opened) == 1 and thread["size"] == 12_000 and thread["id"] == "s-1"

    # none running: a run of its own goes on with the session
    claude.live.clear()
    started = []

    async def run(args, line, room, timeout, files=None, program=None):
        started.append((args, line))
        return Run(printed({"type": "system", "subtype": "compact_boundary", "compact_metadata": {"trigger": "manual", "post_tokens": 9_000}},
                           {"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1", "result": ""}))
    monkeypatch.setattr(claude, "_run", run)
    told = []
    thread = {"key": "k2", "id": "s-1", "record": lambda kind, text="", data=None: told.append(kind)}
    assert asyncio.run(claude.compact(dict(s, window=1_000_000), thread)) == 9_000
    args, line = started[0]
    assert args[args.index("--resume") + 1] == "s-1" and told == ["compact"]
    # the command goes on stdin, as the session's message, never as an argument (claude_policy takes a prompt on the command line only for a command)
    assert "/compact" not in args and json.loads(line)["message"] == {"role": "user", "content": "/compact"}

    async def lost(*a, **k):
        return Run(printed({"type": "result", "subtype": "error_during_execution", "is_error": True,
                            "result": "No conversation found with session ID: s-1"}))
    monkeypatch.setattr(claude, "_run", lost)
    with pytest.raises(claude.Lost):
        asyncio.run(claude.compact(s, {"key": "k3", "id": "s-1"}))
    with pytest.raises(claude.Failed):
        asyncio.run(claude.compact(s, {"key": "k4", "id": None}))


def test_a_session_row_keeps_its_story_and_says_how_full_it_is(tmp_path):
    from scene import refs, sessions
    state = state_with_a_user(tmp_path)
    row = sessions.open_row(state.db, 1, 3, "tab1", "claude/sonnet", 1_000_000)
    assert refs.looks_like(row["ref"], refs.SESSION) and row["agent"] == "AGTtab1"
    assert sessions.open_row(state.db, 1, 3, "tab1", "claude/opus", 1_000_000)["id"] == row["id"]   # one for the tab
    assert sessions.open_row(state.db, 1, 0, "tab1", "claude/opus", 1_000_000)["id"] != row["id"]   # all work: its own
    sessions.record(state.db, row["id"], "user", "hello")
    sessions.record(state.db, row["id"], "tool_call", "find_assets", {"input": {"query": "Mira"}})
    sessions.update(state.db, row["id"], claude_id="s-1", messages=1, context_tokens=850_000)
    sessions.update(state.db, row["id"], compacts=1)
    found = sessions.one(state.db, row["ref"])
    assert found["claude_id"] == "s-1" and found["messages"] == 1 and found["compacts"] == 1 and found["user_name"] == "A"
    first, second = sessions.events(state.db, row["id"])
    assert (first["kind"], second["data"]) == ("user", {"input": {"query": "Mira"}})
    assert [e["kind"] for e in sessions.events(state.db, row["id"], after=first["id"])] == ["tool_call"]
    assert [r["ref"] for r in sessions.listing(state.db, q="s-1")] == [row["ref"]] and sessions.listing(state.db, q="nobody") == []
    assert sessions.context(850_000, 1_000_000) == {"tokens": 850_000, "window": 1_000_000, "percent": 85, "offer": True}
    assert sessions.context(500_000, 1_000_000)["offer"] is False and sessions.context(5, 0)["percent"] == 0
    assert sessions.title("Agent 2", "Film › Episode 1", "Ada") == "Studio · Agent 2 · Film › Episode 1 · Ada"


def test_each_model_offers_the_effort_levels_it_takes():
    assert claude.efforts("claude/opus") == (list(claude.LEVELS), "medium")            # "opus" is Opus 5.5
    assert claude.efforts("claude/sonnet") == (list(claude.LEVELS), "high")
    assert claude.efforts("haiku") == (list(claude.LEVELS), "medium")
    assert claude.efforts("claude-opus-4-6") == (["low", "medium", "high", "max"], "high")
    assert claude.efforts("claude-opus-4-5") == (["low", "medium", "high"], "high")
    assert claude.efforts("claude-haiku-4-5") == ([], None) and claude.efforts("claude-sonnet-4-5") == ([], None)
    assert claude.chosen_effort("claude/opus", "XHIGH") == "xhigh"
    assert claude.chosen_effort("claude-opus-4-6", "xhigh") == "" and claude.chosen_effort("claude/opus", "turbo") == ""


def test_the_effort_picked_goes_to_the_conversation_and_not_to_the_small_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(claude, "sdk", None)
    brain = brain_with_claude()
    brain.services["claude"]["home"] = str(tmp_path / "sessions")
    runs = fake_claude(monkeypatch, printed(session_answer({"reply": "Hello.", "steps": []})), printed(answered({"reply": "On its own."})))
    token = claude.EFFORT.set("xhigh")
    try:
        asyncio.run(brain.ask("You plan.", "hi", [], model="claude/sonnet", thread={"id": None}))
        asyncio.run(brain.ask("You plan.", "hi", [], model="claude/sonnet"))     # a call of its own: the model's default
    finally:
        claude.EFFORT.reset(token)
    first, second = runs[0]["args"], runs[1]["args"]
    assert first[first.index("--effort") + 1] == "xhigh" and "--effort" not in second


def test_a_live_session_opens_again_with_the_new_effort(monkeypatch):
    brain = brain_with_claude()
    opened = fake_live(monkeypatch, [result(dict(PLAN, reply="a"))], [result(dict(PLAN, reply="b"))])
    thread = {"key": "1:tab1:3:claude/opus", "id": None}

    def say(text, effort):
        token = claude.EFFORT.set(effort)
        try:
            asyncio.run(brain.ask_with_tools("You plan.", text, ["w"], {}, model="claude/sonnet", thread=thread))
        finally:
            claude.EFFORT.reset(token)
    say("one", "")
    say("two", "max")
    assert opened[0].settings["effort"] == "" and opened[0].closed
    assert opened[1].settings["effort"] == "max" and opened[1].settings["resume"] == "s-1"   # the same conversation goes on

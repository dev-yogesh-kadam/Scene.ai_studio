"""The agent tabs' Claude sessions as admins watch them (the console's Sessions section, sessions.py): every session
with who, where and how full it is, and what happened in it in order. Admins only, and watch only."""

from scene import claude, sessions
from test_api import ADMIN, console, register
from test_staff_roles import staff_member


def a_session(client, user_id, project_id=0):
    db = client.app.state.db
    row = sessions.open_row(db, user_id, project_id, "tab1", "claude/sonnet", 1_000_000)
    sessions.record(db, row["id"], "user", "make a fox")
    sessions.record(db, row["id"], "tool_call", "find_assets", {"input": {"query": "fox"}})
    sessions.record(db, row["id"], "answer", "Here is the plan.", {"steps": 1})
    sessions.update(db, row["id"], claude_id="1f2e3d4c-aaaa-bbbb-cccc-1234567890ab", messages=1, context_tokens=820_000,
                    title="Studio · Agent 1 · Film · Ada")
    return row


def test_admins_see_every_session_and_what_happened_in_it(client):
    me = register(client)
    film = client.post("/api/projects", json={"name": "Film"}).json()
    row = a_session(client, me["id"], film["id"])
    desk = console(client)
    listed = desk.get("/api/admin/sessions").json()
    first = listed["sessions"][0]
    assert first["ref"] == row["ref"] and first["user_email"] == ADMIN["email"] and first["project_ref"] == film["ref"]
    assert first["state"] == "idle" and first["percent"] == 82 and listed["counts"] == {"idle": 1}
    assert "claude --resume 1f2e3d4c-aaaa-bbbb-cccc-1234567890ab" in first["resume"]
    assert [s["ref"] for s in desk.get("/api/admin/sessions?q=" + film["ref"]).json()["sessions"]] == [row["ref"]]
    assert desk.get("/api/admin/sessions?state=live").json()["sessions"] == []

    story = desk.get("/api/admin/sessions/" + row["ref"]).json()
    assert [e["kind"] for e in story["events"]] == ["user", "tool_call", "answer"] and story["more"] is False
    assert story["events"][1]["data"] == {"input": {"query": "fox"}}
    newer = desk.get("/api/admin/sessions/{}?after={}".format(row["ref"], story["events"][0]["id"])).json()["events"]
    assert [e["kind"] for e in newer] == ["tool_call", "answer"]
    assert desk.get("/api/admin/sessions/SES0000000000000").status_code == 404

    class Busy:
        class lock:
            locked = staticmethod(lambda: True)
    claude.live["{}:tab1:{}".format(me["id"], film["id"])] = Busy
    try:
        assert desk.get("/api/admin/sessions").json()["sessions"][0]["state"] == "answering"
    finally:
        claude.live.clear()


def test_only_admins_see_sessions(client):
    desk, _, _ = staff_member(client, "support")
    assert desk.get("/api/admin/sessions").status_code == 403
    assert "sessions" not in desk.get("/api/console/me").json()["sections"]


def test_the_console_answers_at_a_sessions_address(client):
    register(client)
    page = console(client).get("/sessions/SESabcdefghijklm")
    assert page.status_code == 200 and "<html" in page.text.lower()


def test_a_tabs_messages_go_on_in_one_session_that_is_recorded_and_compacted(client, monkeypatch, tmp_path):
    me = register(client)
    brain = client.app.state.agent
    brain.services["claude"] = {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": ["sonnet", "opus"], "only": "",
                                "cli": "claude.exe", "timeout": 60, "fast": "", "home": str(tmp_path), "window": 1_000_000}
    sizes = [850_000, 920_000, 100_000]
    seen = []

    async def ask_with_tools(system, message, workflow_ids, tools, finishing=None, rounds=0, thread=None, model=None, **kw):
        seen.append({"message": message, "id": thread.get("id"), "model": model})
        thread["record"]("text", "Thinking out loud")
        thread.update(id="s-1", size=sizes.pop(0))
        return {"reply": "Answer {}".format(len(seen)), "steps": [], "thought": "", "direction": "", "question": None,
                "tools": [], "tokens": {}, "model": model}

    compacted, renamed = [], []

    async def compact(s, thread):
        compacted.append(thread["id"])
        thread["record"]("compact", "Compacted the context (manual)", {"pre_tokens": thread["size"], "post_tokens": 30_000})
        thread["size"] = 30_000
        return 30_000

    async def rename(s, thread, title):
        renamed.append(title)

    monkeypatch.setattr(brain, "ask_with_tools", ask_with_tools)
    monkeypatch.setattr(claude, "compact", compact)
    monkeypatch.setattr(claude, "rename", rename)
    film = client.post("/api/projects", json={"name": "Film"}).json()

    def say(text, model, history):
        return client.post("/api/agent/plan", json={"instruction": text, "project_id": film["id"], "run": "tab1", "tab": "Agent 1",
                                                     "model": model, "history": history}).json()

    first = say("make a fox", "claude/sonnet", [])
    assert first["reply"] == "Answer 1" and first["context"] == {"tokens": 850_000, "window": 1_000_000, "percent": 85, "offer": True}
    assert renamed == ["Studio · Agent 1 · Film · Ada"]
    history = [{"instruction": "make a fox", "reply": "Answer 1"}, {"instruction": "gemini turn", "reply": "From Gemini"}]
    second = say("now at night", "claude/opus", history)                 # another Claude model, after a Gemini turn
    assert seen[1]["id"] == "s-1" and "another model answered" in seen[1]["message"] and "From Gemini" in seen[1]["message"]
    assert second["context"]["percent"] == 92 and compacted == []                   # 92%: compacted before the next one
    history.append({"instruction": "now at night", "reply": "Answer 2"})
    say("one more", "claude/opus", history)                              # past 90% after the last one: compacted first
    assert compacted == ["s-1"] and seen[2]["id"] == "s-1" and len(renamed) == 1

    desk = console(client)
    row = desk.get("/api/admin/sessions").json()["sessions"][0]
    assert row["claude_id"] == "s-1" and row["messages"] == 3 and row["compacts"] == 1 and row["model"] == "claude/opus"
    assert row["title"] == "Studio · Agent 1 · Film · Ada" and row["agent"] == "AGTtab1"
    kinds = [e["kind"] for e in desk.get("/api/admin/sessions/" + row["ref"]).json()["events"]]
    assert kinds[:4] == ["user", "prompt", "text", "answer"]
    assert "model" in kinds and "note" in kinds and "compact" in kinds and kinds.count("user") == 3

    # "Compact now" from the panel: the tab's session, compacted, and its row told how full it is now (read and kept on
    # the database's threads: they were read on the event loop, which the tests' loop guard refuses)
    done = client.post("/api/agent/session/compact", json={"run": "tab1", "project_id": film["id"]})
    assert done.status_code == 200 and done.json()["context"]["tokens"] == 30_000 and compacted == ["s-1", "s-1"]


def test_the_agents_async_code_never_waits_on_the_database_in_the_event_loop():
    """A plain call of runs, sessions or conversations (each queries the database) inside an async function of
    api/workspace.py would block the event loop: they go through offload. Read from the source, so a path no test
    reaches (a skill handed on in a long run) is checked too."""
    import ast
    from pathlib import Path
    from scene.api import workspace
    tree = ast.parse(Path(workspace.__file__).read_text(encoding="utf-8"))
    queries = {"runs": ("kept_thread", "keep_thread", "threads_of", "kept_skill", "keep_skill", "kept_attached", "keep_attached",
                        "read", "write", "delete", "leaves"),
               "sessions": ("open_row", "record", "update", "listing", "one", "events"),
               "conversations": ("read", "write", "delete", "waiting"),
               "state.db": ("one", "all", "run", "change", "setting", "set_setting"),
               "request.app.state.db": ("one", "all", "run", "change", "setting", "set_setting")}
    found = []

    def walk(node, in_async):
        for child in ast.iter_child_nodes(node):
            inside = isinstance(child, ast.AsyncFunctionDef) or (in_async and not isinstance(child, (ast.FunctionDef, ast.Lambda)))
            if inside and isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) \
                    and child.func.attr in queries.get(ast.unparse(child.func.value), ()):
                found.append("{}: {}".format(child.lineno, ast.unparse(child.func)))
            walk(child, inside)
    walk(tree, False)
    assert found == []

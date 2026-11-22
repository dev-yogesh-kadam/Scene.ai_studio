"""Everything the agent remembers or reads belongs to one module (a project's module, or its main canvas): the user's
memory (recall.py), the catalogue and its "$state:/assets/<id>" references (core.py), the library items its tools read
(kit.item_in_module), and a tab's own run state (runs.py). What is set up in module A is never seen from module B."""

import pytest

from scene import core, recall, runs
from test_agent_shots import hosted
from test_sharing import setup, upload


def db_of(client):
    return client.app.state.db


def modules(client):
    """Ada, signed in, with "Film" and two modules of it, A and B; Film has one picture (setup), A one too."""
    ada, film = setup(client)
    a = client.post("/api/projects", json={"name": "A", "parent_id": film}).json()["id"]
    b = client.post("/api/projects", json={"name": "B", "parent_id": film}).json()["id"]
    assert upload(client, a).status_code == 200
    return ada, film, a, b


def told(seen):
    return [m["content"] for m in seen[-1] if m["role"] == "user"]


def text_in(client, project, words="INT. LIGHTHOUSE - NIGHT. The keeper climbs."):
    made = client.post("/api/library/upload", files={"file": ("script.txt", words.encode("utf-8"), "text/plain")},
                       data={"project_id": str(project)})
    assert made.status_code == 200
    return db_of(client).one("SELECT id FROM generations WHERE project_id = ? AND kind = 'text' ORDER BY id DESC", (project,))["id"]


def test_memory_saved_in_one_module_is_not_in_another(client, monkeypatch):
    ada, film, a, b = modules(client)
    hosted(monkeypatch, client, {"tool": "memory", "op": "remember", "path": "pref.shape", "value": "portrait, for Reels"},
           {"tool": "finish", "reply": "Noted.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "I always post Reels", "project_id": a})
    db = db_of(client)
    assert [e["key"] for e in recall.entries(db, ada["id"], a)] == ["pref.shape"]
    # module B: not in its digest, not found by recall, not listed by the Memory view
    assert recall.digest(db, ada["id"], b) == "" and recall.recall(db, ada["id"], b, "portrait") == []
    assert client.get("/api/remembered", params={"project": b}).json()["entries"] == []
    assert client.get("/api/remembered", params={"project": film}).json()["entries"] == []
    seen = hosted(monkeypatch, client, {"tool": "memory", "op": "recall", "value": "portrait"}, {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "a dog video", "project_id": b})
    assert not any("portrait, for Reels" in m["content"] for m in seen[-1])
    assert any(t.startswith("Result of memory:") and "Nothing remembered like that." in t for t in told(seen))
    # forgetting in B leaves A's as it is; the same key in B is B's own
    assert client.delete("/api/remembered", params={"project": b, "key": "pref.shape"}).json()["forgotten"] is False
    recall.remember(db, ada["id"], b, "pref.shape", "landscape")
    assert recall.digest(db, ada["id"], a) == "pref.shape: portrait, for Reels"
    assert recall.digest(db, ada["id"], b) == "pref.shape: landscape"


def test_outside_a_project_the_memory_tool_refuses_and_no_digest_is_sent(client, monkeypatch):
    ada, film, a, b = modules(client)
    recall.remember(db_of(client), ada["id"], a, "pref.shape", "portrait, for Reels")
    seen = hosted(monkeypatch, client, {"tool": "memory", "op": "remember", "path": "pref.light", "value": "soft"},
                  {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "remember I like soft light"})
    assert any(t.startswith("Result of memory:") and recall.NO_MODULE in t for t in told(seen))
    assert not any("portrait, for Reels" in m["content"] or "Memory, what you know" in m["content"] for m in seen[-1])
    assert db_of(client).one("SELECT COUNT(*) AS n FROM user_memory")["n"] == 1   # only A's
    with pytest.raises(recall.RecallError, match="belongs to a module"):
        recall.remember(db_of(client), ada["id"], 0, "pref.light", "soft")
    assert recall.digest(db_of(client), ada["id"], 0) == "" and recall.entries(db_of(client), ada["id"], 0) == []


def test_the_memory_of_a_module_is_only_shown_to_people_in_its_project(client):
    from test_sharing import BOB, as_
    ada, film, a, b = modules(client)
    recall.remember(db_of(client), ada["id"], a, "pref.shape", "portrait")
    as_(client, BOB)
    assert client.get("/api/remembered", params={"project": a}).status_code == 404


def test_a_record_of_another_module_is_not_in_the_catalogue(client):
    ada, film, a, b = modules(client)
    db = db_of(client)
    item = db.one("SELECT id FROM generations WHERE project_id = ?", (a,))["id"]
    in_a = core.Core(db, ada["id"], "tab1", a)
    pid = in_a.read("/assets/{}".format(item))["value"]["id"]
    in_b = core.Core(db, ada["id"], "tab1", b)
    assert in_b.read("/assets/" + pid)["missing"] is True
    assert in_b.read("/assets/{}".format(item))["missing"] is True
    with pytest.raises(runs.RunError, match="state_reference_unresolved|does not hold|nothing"):
        in_b.resolve("$state:/assets/{}/url".format(pid))
    with pytest.raises(runs.RunError, match="There is nothing at"):
        in_b.write("/assets/{}/facts".format(pid), {"has_person": True})
    assert "facts" not in in_a.read("/assets/" + pid)["value"]   # nothing was written on A's record
    # nor from the project's main canvas, nor from outside any project
    assert core.Core(db, ada["id"], "tab1", film).read("/assets/" + pid)["missing"] is True
    assert core.Core(db, ada["id"], "tab1", 0).read("/assets/" + pid)["missing"] is True


def test_an_item_of_another_module_is_refused_by_the_agents_tools(client, monkeypatch):
    ada, film, a, b = modules(client)
    db = db_of(client)
    script = text_in(client, a)
    picture = db.one("SELECT id FROM generations WHERE project_id = ? AND kind = 'image'", (a,))["id"]
    seen = hosted(monkeypatch, client, {"tool": "read_text", "item": script},
                  {"tool": "review", "item": picture},
                  {"tool": "second_opinion", "text": "is this good?", "item": picture},
                  {"tool": "finish", "reply": "ok", "steps": []})
    plan = client.post("/api/agent/plan", json={"instruction": "@1 read my script", "selection": [script], "project_id": b}).json()
    results = [t for t in told(seen) if t.startswith("Result of")]
    assert len(results) == 3 and all("That item is in another module; attach it here first." in t for t in results)
    assert not any("The keeper climbs" in m["content"] for m in seen[-1])          # the attachment was not read either
    assert any("another module" in e["text"] for e in plan["activity"])
    # in A itself the same calls read it
    seen = hosted(monkeypatch, client, {"tool": "read_text", "item": script}, {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "read my script", "project_id": a})
    assert any(t.startswith("Result of read_text:") and "The keeper climbs" in t for t in told(seen))


def test_an_item_is_in_its_own_module_only(client):
    from scene import kit
    ada, film, a, b = modules(client)
    db = db_of(client)
    item = db.one("SELECT id FROM generations WHERE project_id = ?", (a,))["id"]
    assert kit.item_in_module(db, ada["id"], a, item)["id"] == item
    assert kit.item_in_module(db, ada["id"], a, item, "text") is None
    assert kit.item_in_module(db, ada["id"], b, item) is None
    assert kit.item_in_module(db, ada["id"], film, item) is None
    assert kit.item_in_module(db, ada["id"], 0, item) is None
    assert kit.refusal(db, ada["id"], item, "No such item.") == kit.ELSEWHERE
    assert kit.refusal(db, ada["id"], 999999, "No such item.") == "No such item."


def test_the_same_tab_keeps_its_skill_and_files_apart_in_each_module(client):
    ada, film, a, b = modules(client)
    db = db_of(client)
    runs.keep_skill(db, ada["id"], "tab1", a, "script-to-video")
    runs.keep_attached(db, ada["id"], "tab1", a, [1, 2])
    runs.mark(db, ada["id"], "tab1", a, "brief_asked")
    assert runs.kept_skill(db, ada["id"], "tab1", a) == "script-to-video"
    assert runs.kept_attached(db, ada["id"], "tab1", a) == [1, 2]
    assert runs.marked(db, ada["id"], "tab1", a, "brief_asked") is True
    assert runs.kept_skill(db, ada["id"], "tab1", b) is None
    assert runs.kept_attached(db, ada["id"], "tab1", b) == []
    assert runs.marked(db, ada["id"], "tab1", b, "brief_asked") is None
    runs.keep_skill(db, ada["id"], "tab1", b, "pocket-motion")
    assert runs.kept_skill(db, ada["id"], "tab1", a) == "script-to-video"
    # a tab that kept its skill before tabs kept one for each module (a value at /skill itself) is not stuck on it
    runs.write(db, ada["id"], "tab2", runs.SKILL, "old-skill", "studio", trusted=True)
    runs.keep_skill(db, ada["id"], "tab2", a, "script-to-video")
    assert runs.kept_skill(db, ada["id"], "tab2", a) == "script-to-video"
    assert runs.read(db, ada["id"], "tab2", runs.SKILL)["folder"] is True
    with pytest.raises(runs.RunError, match="kept by the studio"):
        runs.write(db, ada["id"], "tab1", "/skill/p{}".format(a), "other")


def test_a_long_run_carries_its_skill_on_only_in_its_own_module(client, monkeypatch):
    ada, film, a, b = modules(client)
    hosted(monkeypatch, client, {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "/script-to-video a film about a lighthouse", "project_id": a, "run": "tab9"})
    db = db_of(client)
    assert runs.kept_skill(db, ada["id"], "tab9", a) == "story-to-screen"   # the old name finds the skill by its new one
    hosted(monkeypatch, client, {"tool": "finish", "reply": "ok", "steps": []})
    plan = client.post("/api/agent/plan", json={"instruction": "go", "project_id": b, "run": "tab9"}).json()
    assert not any(e["text"].startswith("Carried on with") for e in plan["activity"])
    assert runs.kept_skill(db, ada["id"], "tab9", b) is None

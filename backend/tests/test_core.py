"""NeuralCore's memory (core.py): a module's memory shared by every tab and member of it and by no other module, the
tab's own paths, the cast, the asset catalogue with its random ids and lineage, and state references."""

import pytest

from scene import core, runs
from test_agent_shots import hosted
from test_api import register
from test_sharing import BOB, CAT, as_, setup, upload


def db_of(client):
    return client.app.state.db


def module_of(client, film, name="Episode 1"):
    return client.post("/api/projects", json={"name": name, "parent_id": film}).json()["id"]


def add(client, film, who, role):
    client.post("/api/projects/{}/members".format(film), json={"people": [{"email": who["email"], "role": role}]})


def test_an_episode_is_shared_by_every_tab_and_member(client):
    ada, film = setup(client)
    one, two = module_of(client, film), module_of(client, film, "Episode 2")
    add(client, film, BOB, "creator")
    add(client, film, CAT, "viewer")
    db = db_of(client)
    bob, cat = (db.one("SELECT id FROM users WHERE email = ?", (w["email"],))["id"] for w in (BOB, CAT))
    core.Core(db, ada["id"], "tab1", one).write("/scenes/1/summary", "Meera finds the dog")
    # another tab, and another member, see the same episode
    assert core.Core(db, ada["id"], "tab2", one).read("/scenes/1/summary")["value"] == "Meera finds the dog"
    as_(client, BOB)
    bobs = core.Core(db, bob, "bobtab", one)
    assert bobs.read("/scenes/1/summary")["value"] == "Meera finds the dog"
    bobs.write("/scenes/2/summary", "The mother says no")
    # another module of the project has a memory of its own, and none of the others can be reached from it
    assert core.Core(db, ada["id"], "tab1", two).read("/scenes/1/summary")["missing"] is True
    assert core.Core(db, ada["id"], "tab1", film).read("/scenes/1/summary")["missing"] is True   # nor the main canvas
    with pytest.raises(runs.RunError, match="belongs to this module alone"):
        bobs.write("@show/style/description", "warm 35mm film")
    # a viewer reads but does not write
    as_(client, CAT)
    cats = core.Core(db, cat, "cattab", one)
    assert cats.read("/scenes/2/summary")["value"] == "The mother says no"
    with pytest.raises(runs.RunError, match="read only"):
        cats.write("/scenes/3/summary", "x")
    # the tab keeps its own paths: the skill a tab follows is not another tab's
    runs.keep_skill(db, ada["id"], "tab1", one, "pocket-motion")
    assert core.Core(db, ada["id"], "tab1", one).read("/skill/p{}".format(one))["value"] == "pocket-motion"
    assert core.Core(db, ada["id"], "tab2", one).read("/skill/p{}".format(one))["missing"] is True
    with pytest.raises(runs.RunError, match="kept by the studio"):
        core.Core(db, ada["id"], "tab1", one).write("/skill/p{}".format(one), "other")


def test_another_projects_memory_cannot_be_read(client):
    ada, film = setup(client)
    other = client.post("/api/projects", json={"name": "Other"}).json()
    db = db_of(client)
    core.Core(db, ada["id"], "tab1", other["id"]).write("/characters/meera/description", "about twenty, red scarf")
    here = core.Core(db, ada["id"], "tab1", film)
    ref = db.one("SELECT ref FROM projects WHERE id = ?", (other["id"],))["ref"]
    with pytest.raises(runs.RunError, match="belongs to this module alone"):
        here.read("@{}/characters/meera/description".format(ref))
    with pytest.raises(runs.RunError, match="A state reference"):
        here.resolve("$state:@{}/characters/meera/description".format(ref))
    assert here.read("/characters/meera/description")["missing"] is True


def test_a_tabs_own_run_moves_into_the_episode_once(client):
    ada, film = setup(client)
    db = db_of(client)
    runs.write(db, ada["id"], "tab1", "/motion/status", "step 3")
    runs.keep_skill(db, ada["id"], "tab1", film, "pocket-motion")
    shared = core.Core(db, ada["id"], "tab1", film)
    assert shared.adopt() == 1
    assert shared.read("/motion/status")["value"] == "step 3"
    assert shared.read("/skill/p{}".format(film))["value"] == "pocket-motion"      # the tab's own stays the tab's
    assert core.Core(db, ada["id"], "tab1", film).adopt() == 0    # once
    # outside a project the tab's run holds everything, as before
    loose = core.Core(db, ada["id"], "tab9", 0)
    loose.write("/motion/status", "alone")
    assert runs.read(db, ada["id"], "tab9", "/motion/status")["value"] == "alone"
    with pytest.raises(runs.RunError, match="keeps no memory"):
        core.Core(db, ada["id"], "", 0).write("/x", 1)


def test_the_catalogue_reads_every_item_and_keeps_facts(client):
    ada, film = setup(client)
    db = db_of(client)
    item = db.one("SELECT id FROM generations WHERE project_id = ?", (film,))["id"]
    shared = core.Core(db, ada["id"], "tab1", film)
    # listed, every record has twelve random hex digits for its id, and says how it came to be
    [listed] = shared.catalogue()["records"]
    pid = listed["id"]
    assert core.PUBLIC.fullmatch(pid) and listed["item"] == item and listed["origin"] == "upload"
    assert listed["mime_type"] == "image/png" and listed["url"] == "/api/library/{}/file".format(item)
    assert shared.catalogue()["records"][0]["id"] == pid                       # given once, kept
    record = shared.read("/assets/" + pid)["value"]
    assert record["item"] == item and record["kind"] == "image" and "facts" not in record
    assert shared.read("/assets/{}".format(item))["value"]["id"] == pid        # the library id names it too
    shared.write("/assets/{}/facts".format(pid), {"has_person": True, "scene": "night market", "tags": ["hero"]})
    shared.write("/assets/{}/facts".format(pid), {"photoreal": False})          # merged into what it has
    assert shared.read("/assets/{}/facts".format(pid))["value"] == {"has_person": True, "scene": "night market",
                                                                    "tags": {"hero": True}, "photoreal": False}
    with pytest.raises(runs.RunError, match="true or false"):
        shared.write("/assets/{}/facts".format(pid), {"has_person": "yes"})
    with pytest.raises(runs.RunError, match="only /assets/<id>/facts"):
        shared.write("/assets/{}/name".format(pid), "x")
    page = shared.read("/assets")
    assert page["folder"] and page["leaves"][0]["path"] == "/assets/" + pid
    assert shared.resolve("$state:/assets/{}/url".format(pid)) == item
    shared.write("/clips/c1/url", "$state:/assets/{}/url".format(pid))         # a note names the file by its record
    assert shared.resolve("$state:/clips/c1/url") == item
    # a member sees the project's items; someone outside it does not
    as_(client, BOB)
    bob = db.one("SELECT id FROM users WHERE email = ?", (BOB["email"],))["id"]
    assert core.Core(db, bob, "bobtab", 0).read("/assets/" + pid)["missing"] is True


def test_the_catalogue_says_what_a_working_file_was_made_from(client):
    ada, film = setup(client)
    db = db_of(client)
    source = db.one("SELECT id FROM generations WHERE project_id = ?", (film,))["id"]
    db.run("INSERT INTO generations (user_id, project_id, workflow, kind, name, filename, settings, context, created) "
           "VALUES (?, ?, 'edit/reference', 'image', 'Ref at 1500 px', 'ref.png', ?, '{}', 1)", (ada["id"], film, '{"image": %d}' % source))
    shared = core.Core(db, ada["id"], "tab1", film)
    made, first = shared.catalogue()["records"][:2]
    assert made["origin"] == "reference" and made["tool"] == "edit/reference" and made["source_asset_id"] == first["id"]


def test_references_are_resolved_whole_and_inside_a_text(client):
    ada, film = setup(client)
    db = db_of(client)
    shared = core.Core(db, ada["id"], "tab1", film)
    shared.write("/characters/meera/description", "a girl of about twenty in a yellow raincoat")
    shared.write("/videos/1/item", {"item": 42})
    assert shared.fill_text("Close-up: $state:/characters/meera/description, smiling.") == \
        "Close-up: a girl of about twenty in a yellow raincoat, smiling."
    assert shared.resolve_all({"clips": ["$state:/videos/1/item"]}) == {"clips": [42]}
    with pytest.raises(runs.RunError, match="state_reference_unresolved"):
        shared.fill_text("$state:/characters/nobody/description")


def test_the_agent_writes_the_episode_and_another_tab_reads_it(client, monkeypatch):
    ada, film = setup(client)
    seen = hosted(monkeypatch, client, {"tool": "state_write", "path": "/scenes/1/summary", "value": '"the chase"'},
                  {"tool": "finish", "reply": "Saved.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "save the scene", "run": "tab1", "project_id": film})
    assert any("Written: /scenes/1/summary" in m["content"] for m in seen[-1] if m["role"] == "user")
    seen = hosted(monkeypatch, client, {"tool": "state_read", "path": "/scenes/1/summary"}, {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "what is scene 1?", "run": "tab2", "project_id": film})
    assert any('"the chase"' in m["content"] for m in seen[-1] if m["role"] == "user")


def test_a_step_takes_words_from_the_state_and_keeps_its_result_there(client, monkeypatch):
    from test_agent_conversation import STEP
    ada, film = setup(client)
    db = db_of(client)
    core.Core(db, ada["id"], "tab1", film).write("/characters/maya/description", "a girl of about twenty in a yellow raincoat")
    step = dict(STEP, prompt="$state:/characters/maya/description runs through the rain.", save_to="/videos/1")
    hosted(monkeypatch, client, {"tool": "finish", "reply": "One shot.", "steps": [step]})
    plan = client.post("/api/agent/plan", json={"instruction": "maya runs", "run": "tab1", "project_id": film}).json()
    [made] = plan["steps"]
    assert "a girl of about twenty in a yellow raincoat runs through the rain" in made["prompt"]
    slot = made["settings"]["save_to_state"]
    assert slot["path"] == "/videos/1" and slot["run"] == core.EPISODE.format(film)
    # once made, the result is kept there; a retake moves the first one to takes/1
    assert core.keep_take(db, ada["id"], slot, 101) == "/videos/1/item"
    assert core.keep_take(db, ada["id"], slot, 102) == "/videos/1/item"
    shared = core.Core(db, ada["id"], "tab2", film)
    assert shared.resolve("$state:/videos/1/item") == 102
    assert shared.read("/videos/1/takes/1")["value"]["item"] == 101
    assert shared.read("/videos/1/item")["value"]["url"].startswith("$state:/assets/")
    # a slot is checked again for the job's user: someone outside the project writes nothing there
    bob = db.one("SELECT id FROM users WHERE email = ?", (BOB["email"],))["id"]
    assert core.keep_take(db, bob, slot, 103) is None
    assert core.keep_take(db, ada["id"], dict(slot, path="/skill"), 104) is None


def test_a_step_naming_state_that_is_not_there_is_left_out_with_the_reason(client, monkeypatch):
    from test_agent_conversation import STEP
    ada, film = setup(client)
    seen = hosted(monkeypatch, client,
                  {"tool": "finish", "reply": "One shot.", "steps": [dict(STEP, prompt="$state:/characters/nobody/description waves.")]},
                  {"tool": "finish", "reply": "One shot.", "steps": [STEP]})
    plan = client.post("/api/agent/plan", json={"instruction": "a wave", "run": "tab1", "project_id": film}).json()
    assert any("state_reference_unresolved" in m["content"] for m in seen[-1] if m["role"] == "user")
    assert [s["name"] for s in plan["steps"]] == ["Dog in the park"]


def test_each_module_has_a_neuralcore_of_its_own(client, monkeypatch):
    ada, film = setup(client)
    one, two = module_of(client, film), module_of(client, film, "Episode 2")
    upload(client, one)
    item = db_of(client).one("SELECT id FROM generations WHERE project_id = ? ORDER BY id DESC", (one,))["id"]
    hosted(monkeypatch, client, {"tool": "book_save", "item": item, "text": "Maya", "op": "character", "settings": "always"},
           {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "keep maya", "project_id": one})
    [maya] = client.get("/api/kit", params={"project": one}).json()["entries"]
    # module one has her; module two and the main canvas never see her
    from scene import kit
    assert [e["name"] for e in kit.always(db_of(client), ada["id"], one)] == ["Maya"]
    assert client.get("/api/kit", params={"project": two}).json()["entries"] == []
    assert kit.entries(db_of(client), ada["id"], film) == []
    cast = core.Core(db_of(client), ada["id"], "tab1", one).read("/cast/maya")["value"]
    assert cast["type"] == "character" and cast["ref"].startswith("$state:/assets/") and cast["entry"] == maya["id"]
    assert core.Core(db_of(client), ada["id"], "tab1", two).read("/cast")["value"] == {}
    with pytest.raises(runs.RunError, match="book_save"):
        core.Core(db_of(client), ada["id"], "tab1", one).write("/cast/maya/type", "prop")
    # the agent in module two cannot change module one's entry by its id
    seen = hosted(monkeypatch, client, {"tool": "book_save", "asset": maya["id"], "text": "Maya Rao", "op": "character"},
                  {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "rename maya", "project_id": two})
    assert any("in this module" in m["content"] for m in seen[-1] if m["role"] == "user")
    assert [e["name"] for e in kit.entries(db_of(client), ada["id"], one)] == ["Maya"]
    # deleting module one takes its NeuralCore with it
    assert client.delete("/api/projects/{}".format(one)).status_code == 200
    assert db_of(client).one("SELECT 1 FROM assets WHERE id = ?", (maya["id"],)) is None


def test_an_entry_of_another_project_or_module_is_never_found_or_copied_here(client, monkeypatch):
    ada, film = setup(client)
    other = client.post("/api/projects", json={"name": "Old film"}).json()["id"]
    upload(client, other)
    item = db_of(client).one("SELECT id FROM generations WHERE project_id = ?", (other,))["id"]
    hosted(monkeypatch, client, {"tool": "book_save", "item": item, "text": "Meera", "op": "character", "value": "a girl in a red scarf"},
           {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "keep meera", "project_id": other})
    [meera] = client.get("/api/kit", params={"project": other}).json()["entries"]
    one = module_of(client, film)
    seen = hosted(monkeypatch, client, {"tool": "find_assets", "query": "red scarf", "op": "all"},
                  {"tool": "book_save", "asset": meera["id"], "text": "Meera", "op": "character"},
                  {"tool": "book_save", "item": item, "text": "Meera", "op": "character"},
                  {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "use the girl in the red scarf from my other film", "project_id": one})
    told = [m["content"] for m in seen[-1] if m["role"] == "user"]
    assert not any("Old film" in t for t in told)
    assert any("Nothing in NeuralCore matches" in t for t in told)
    assert any("There is no NeuralCore entry {} in this module".format(meera["id"]) in t for t in told)
    assert any("That item is in another module; attach it here first." in t for t in told)
    assert client.get("/api/kit", params={"project": one}).json()["entries"] == []
    assert client.get("/api/kit", params={"project": film}).json()["entries"] == []
    # the other project's entry is as it was
    [kept] = client.get("/api/kit", params={"project": other}).json()["entries"]
    assert kept["id"] == meera["id"] and kept["name"] == "Meera"


def test_the_agent_remembers_a_user_in_one_module_and_says_what_it_used(client, monkeypatch):
    from scene import recall
    ada, film = setup(client)
    hosted(monkeypatch, client, {"tool": "memory", "op": "remember", "path": "pref.shape", "value": "portrait, for Reels"},
           {"tool": "memory", "op": "remember", "path": "bad key", "value": "x"},
           {"tool": "finish", "reply": "Noted.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "I always post Reels", "project_id": film})
    assert [(e["key"], e["value"]) for e in recall.entries(db_of(client), ada["id"], film)] == [("pref.shape", "portrait, for Reels")]
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Portrait, as you make Reels.\n[from memory: pref.shape, pref.made_up]", "steps": []})
    plan = client.post("/api/agent/plan", json={"instruction": "a dog video", "project_id": film}).json()
    assert any("pref.shape: portrait, for Reels" in m["content"] for m in seen[-1])   # the digest went with the message
    assert plan["reply"] == "Portrait, as you make Reels." and plan["memory_used"] == ["pref.shape"]
    hosted(monkeypatch, client, {"tool": "memory", "op": "forget", "path": "pref.shape"}, {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "stop making everything portrait", "project_id": film})
    assert recall.entries(db_of(client), ada["id"], film) == []


def test_the_memory_view_reads_and_changes_the_state_and_what_is_remembered(client):
    ada, film = setup(client)
    one = module_of(client, film)
    core.Core(db_of(client), ada["id"], "tab1", one).write("/scenes/1/summary", "the chase")
    tree = client.get("/api/core/memory", params={"project": one}).json()
    assert [l["path"] for l in tree["leaves"]] == ["/scenes/1/summary"] and tree["writable"]
    assert tree["cast"] == {} and tree["assets"]["total"] == 0
    assert client.put("/api/core/state", json={"project_id": one, "path": "/scenes/1/summary", "value": "the long chase"}).status_code == 200
    assert core.Core(db_of(client), ada["id"], "tab2", one).read("/scenes/1/summary")["value"] == "the long chase"
    assert client.delete("/api/core/state", params={"project": one, "path": "/scenes/1/summary"}).json()["deleted"] == 1
    from scene import recall
    recall.remember(db_of(client), ada["id"], one, "pref.light", "soft window light")
    assert client.get("/api/remembered", params={"project": one}).json()["entries"][0]["key"] == "pref.light"
    assert client.get("/api/remembered", params={"project": film}).json()["entries"] == []   # the main canvas keeps its own
    assert client.get("/api/remembered").status_code == 400                                 # memory belongs to a module
    assert client.delete("/api/remembered", params={"project": one, "key": "pref.light"}).json()["forgotten"] is True
    as_(client, BOB)   # someone outside the project sees nothing of it
    assert client.get("/api/core/memory", params={"project": one}).status_code == 404

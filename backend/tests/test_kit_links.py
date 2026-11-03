"""How NeuralCore entries hang together (kit.py): a character's looks from a scene on, a location's sheets per time of
day, a palette kept with a location, and relatives by blood or in-law. Set through PUT /api/kit/<id>, read by the panel
and by the agent in /cast."""

import json

from scene import core, kit
from test_agent_shots import hosted
from test_api import register
from test_kit import add, picture


def kit_of(client, project):
    return {e["name"]: e for e in client.get("/api/kit", params={"project": project}).json()["entries"]}


def setup(client):
    me = register(client)
    project = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    made = {}
    for name, type_ in (("Maya", "character"), ("Ira", "character"), ("Dev", "character"), ("Kitchen", "location")):
        made[name] = add(client, picture(client, me["id"], name.lower(), project=project), name, type_, name == "Maya", project)
    return me, project, made


def test_an_entry_named_as_a_look_links_itself_and_never_fills_a_slot_on_its_own(client):
    me, project, made = setup(client)
    torn = add(client, picture(client, me["id"], "maya-torn", project=project), "Maya - torn sleeve", "character", True, project)
    night = add(client, picture(client, me["id"], "kitchen-night", project=project), "Kitchen – night", "location", False, project)
    stray = add(client, picture(client, me["id"], "x", project=project), "Rain - heavy", "location", False, project)
    found = kit_of(client, project)
    assert (found["Maya - torn sleeve"]["look_of"], found["Maya - torn sleeve"]["variant"]) == (made["Maya"]["id"], "torn sleeve")
    assert (found["Kitchen – night"]["look_of"], found["Kitchen – night"]["variant"]) == (made["Kitchen"]["id"], "night")
    assert found["Rain - heavy"]["look_of"] is None   # a dash that names no entry is only a name
    # a look is never always on: the base stands for Maya in every shot, the look only where a shot names it
    assert [e["id"] for e in kit.always(client.app.state.db, me["id"], project)] == [made["Maya"]["id"]]
    assert torn["id"] and night["id"] and stray["id"]


def test_looks_start_in_a_scene_and_a_location_keeps_its_palette(client):
    me, project, made = setup(client)
    torn = add(client, picture(client, me["id"], "maya-torn", project=project), "Maya - torn sleeve", "character", False, project)
    put = lambda asset, **body: client.put("/api/kit/%d" % asset, json=body)
    assert put(torn["id"], from_scene=3).json()["from_scene"] == 3
    shown = put(made["Kitchen"]["id"], palette="cold steel-blue shadows, warm sodium highlights, muted and filmic").json()
    assert shown["palette"].startswith("cold steel-blue")
    assert put(torn["id"], from_scene=-1).status_code == 400
    assert "itself a look" in put(made["Ira"]["id"], look_of=torn["id"]).json()["detail"]
    assert put(made["Maya"]["id"], look_of=made["Maya"]["id"]).status_code == 400
    assert put(made["Maya"]["id"], look_of=999999).status_code == 400
    # set by hand, then taken back: the look is an entry of its own again
    assert put(made["Dev"]["id"], look_of=made["Ira"]["id"], variant="as a child").json()["look_of"] == made["Ira"]["id"]
    assert put(made["Dev"]["id"], look_of=0).json()["look_of"] is None
    words = kit.in_words([dict(kit.entry(client.app.state.db, me["id"], made["Kitchen"]["id"]), about="A narrow kitchen")])
    assert words == "The background: A narrow kitchen, graded to cold steel-blue shadows, warm sodium highlights, muted and filmic."


def test_relatives_by_blood_and_in_law_read_both_ways(client):
    me, project, made = setup(client)
    put = lambda asset, **body: client.put("/api/kit/%d" % asset, json=body)
    answer = put(made["Maya"]["id"], relations=[{"to": made["Ira"]["id"], "relation": "Mother"},
                                               {"to": made["Dev"]["id"], "relation": "husband", "blood": True}])
    assert answer.status_code == 200, answer.text
    assert answer.json()["relations"] == [{"to": made["Ira"]["id"], "relation": "mother", "blood": True},
                                          {"to": made["Dev"]["id"], "relation": "husband", "blood": False}]   # a spouse is never blood
    rows = kit.entries(client.app.state.db, me["id"], project)
    assert kit.family(rows, made["Ira"]["id"]) == [{"entry": made["Maya"]["id"], "name": "Maya", "relation": "child", "blood": True}]
    assert kit.family(rows, made["Dev"]["id"])[0]["relation"] == "spouse"
    assert put(made["Maya"]["id"], relations=[{"to": made["Kitchen"]["id"], "relation": "home"}]).status_code == 400
    assert put(made["Maya"]["id"], relations=[{"to": made["Ira"]["id"]}]).status_code == 400
    # a relative taken out of NeuralCore is forgotten by everyone who named them
    assert client.delete("/api/kit/%d" % made["Ira"]["id"]).status_code == 200
    assert [r["to"] for r in kit_of(client, project)["Maya"]["relations"]] == [made["Dev"]["id"]]


def test_the_agent_reads_looks_palettes_and_relatives_in_the_cast(client):
    me, project, made = setup(client)
    add(client, picture(client, me["id"], "kitchen-night", project=project), "Kitchen - night", "location", False, project)
    client.put("/api/kit/%d" % made["Kitchen"]["id"], json={"palette": "warm tungsten"})
    client.put("/api/kit/%d" % made["Ira"]["id"], json={"relations": [{"to": made["Maya"]["id"], "relation": "daughter"}]})
    cast = core.Core(client.app.state.db, me["id"], "", project).cast()
    assert cast["kitchen"]["looks"] == ["kitchen_night"] and cast["kitchen"]["palette"] == "warm tungsten"
    assert (cast["kitchen_night"]["look_of"], cast["kitchen_night"]["variant"]) == ("kitchen", "night")
    assert cast["ira"]["relatives"] == [{"name": "maya", "relation": "daughter", "blood": True}]
    assert cast["maya"]["relatives"] == [{"name": "ira", "relation": "parent", "blood": True}]


def test_the_agent_sets_looks_palettes_and_relatives_through_book_save(client, monkeypatch):
    me, project, made = setup(client)
    night = picture(client, me["id"], "kitchen-night", project=project)
    seen = hosted(monkeypatch, client,
                  # named as a look: linked to Kitchen by its name alone, with the plain settings of before
                  {"tool": "book_save", "text": "Kitchen - night", "op": "location", "item": night},
                  {"tool": "book_save", "text": "Kitchen", "op": "location", "asset": made["Kitchen"]["id"],
                   "settings": json.dumps({"palette": "cold steel-blue shadows, warm sodium highlights"})},
                  {"tool": "book_save", "text": "Maya", "op": "character", "asset": made["Maya"]["id"],
                   "settings": json.dumps({"relations": [{"to": made["Ira"]["id"], "relation": "mother", "blood": True}]})},
                  {"tool": "book_save", "text": "Maya", "op": "character", "asset": made["Maya"]["id"],
                   "settings": json.dumps({"relations": [{"to": made["Kitchen"]["id"], "relation": "home"}]})},
                  {"tool": "finish", "reply": "ok"})
    client.post("/api/agent/plan", json={"instruction": "keep the cast", "project_id": project})
    found = kit_of(client, project)
    assert (found["Kitchen - night"]["look_of"], found["Kitchen - night"]["variant"]) == (made["Kitchen"]["id"], "night")
    assert found["Kitchen"]["palette"] == "cold steel-blue shadows, warm sodium highlights"
    assert found["Maya"]["relations"] == [{"to": made["Ira"]["id"], "relation": "mother", "blood": True}]   # the wrong one changed nothing
    results = [m["content"] for m in seen[-1] if m["role"] == "user" and m["content"].startswith("Result of book_save")]
    assert "Each relative is another character" in results[-1]   # the model is told why


def test_a_duplicated_project_keeps_its_links_among_its_own_entries(client):
    me, project, made = setup(client)
    add(client, picture(client, me["id"], "maya-torn", project=project), "Maya - torn sleeve", "character", False, project)
    client.put("/api/kit/%d" % made["Maya"]["id"], json={"relations": [{"to": made["Ira"]["id"], "relation": "mother"}]})
    copy = client.post("/api/projects/%d/duplicate" % project).json()
    copy_id = copy.get("id") or copy.get("project", {}).get("id")
    found = kit_of(client, copy_id)
    assert found["Maya - torn sleeve"]["look_of"] == found["Maya"]["id"] != made["Maya"]["id"]
    assert found["Maya"]["relations"] == [{"to": found["Ira"]["id"], "relation": "mother", "blood": True}]

"""Shared memory: NeuralCore the agent plans with, the descriptions its model writes, the uploads and notes it
keeps, and the skills it is given."""

import json

from conftest import a_job
from scene import memory, skills
from test_api import register

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def film(client):
    """The test's project: a NeuralCore belongs to a project, and there is none outside one."""
    if not getattr(client, "film", None):
        client.film = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    return client.film


def save_asset(client, name, tag, use_note="", project=0):
    """An entry of NeuralCore of the test's project (or of the project given)."""
    return client.post("/api/kit", files={"file": (name.lower() + ".png", PNG + name.encode(), "image/png")},
                       data={"name": name, "type": tag, "use_note": use_note, "project_id": str(project or film(client))}).json()["id"]


def library_item(client, user_id, name, kind="image", about="", project=None):
    return client.app.state.db.run(
        "INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, seconds, size, created, about, project_id) "
        "VALUES (?, 'x/y', ?, ?, 'missing', '', '{\"prompt\": \"a quiet harbour at dawn\"}', '{}', 1, 1, 1, ?, ?)", (user_id, kind, name, about, project))


def looks(monkeypatch, client, seen):
    """The agent's model, looking at pictures: it says what it was shown, and the file is never read."""
    async def fake_picture(path):
        return "jpeg"

    async def fake_describe(picture, name="", kind="image"):
        seen.append(name)
        return "A girl of about nine in a yellow raincoat, two braids with red ribbons; a photograph, soft light."
    monkeypatch.setattr(memory, "_picture", fake_picture)
    monkeypatch.setattr(client.app.state.agent, "describe", fake_describe)


def test_the_book_lists_saved_assets_and_the_projects_pictures_and_describes_each_once(client, monkeypatch):
    me = register(client)
    seen = []
    looks(monkeypatch, client, seen)
    meera = save_asset(client, "Meera", "character", "Use her for every shot of the girl.")
    cafe = save_asset(client, "Cafe", "background")
    harbour = library_item(client, me["id"], "Harbour", project=film(client))
    library_item(client, me["id"], "Song", kind="audio", project=film(client))   # a sound is not a picture to reuse

    shown = client.get("/api/memory?project=%d" % film(client)).json()   # NeuralCore; the model looks at what it has not seen yet
    assert [a["name"] for a in shown["assets"]] == ["Meera", "Cafe"] and "made" not in shown
    book = memory.book_for_model(memory.book(client.app.state.db, me["id"], film(client)))
    assert [(e.get("asset"), e.get("item"), e["name"], e["type"]) for e in book] == [
        (meera, None, "Meera", "character"), (cafe, None, "Cafe", "location"),
        (None, harbour, "Harbour", "made in this project")]
    assert book[0]["use"] == "Use her for every shot of the girl."
    assert all(e["shows"].startswith("A girl of about nine") for e in book[:2])
    # The library item's file is missing, so it has no description: the book says what it was made from instead.
    assert "shows" not in book[2] and book[2]["made_from"] == "a quiet harbour at dawn"
    assert sorted(seen) == ["Cafe", "Meera"]

    # The descriptions are kept: the next look at the book asks the model nothing.
    seen.clear()
    client.get("/api/memory?project=%d" % film(client))
    assert seen == []
    listed = {a["name"]: a for a in client.get("/api/kit?project=%d" % film(client)).json()["entries"]}
    assert listed["Meera"]["about"].startswith("A girl of about nine") and listed["Meera"]["use_note"].startswith("Use her")


def test_a_failing_look_does_not_stop_the_plan_and_is_not_tried_again(client, monkeypatch):
    register(client)
    tries = []

    async def blind(picture, name="", kind="image"):
        tries.append(name)
        raise RuntimeError("this model cannot see")

    async def fake_picture(path):
        return "jpeg"
    monkeypatch.setattr(memory, "_picture", fake_picture)
    monkeypatch.setattr(client.app.state.agent, "describe", blind)
    save_asset(client, "Meera", "character")   # looked at as it is added: the look fails
    assert client.get("/api/memory?project=%d" % film(client)).status_code == 200
    client.get("/api/memory?project=%d" % film(client))
    assert tries == ["Meera"]


def test_the_agent_puts_a_saved_asset_it_knows_by_name_into_a_slot(client, monkeypatch):
    me = register(client)
    meera = save_asset(client, "Meera", "character", "Use her for every shot of the girl.")
    cafe = save_asset(client, "Cafe", "background")
    harbour = library_item(client, me["id"], "Harbour", about="A harbour at dawn.", project=film(client))
    looks(monkeypatch, client, [])
    asked = {}

    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        asked.update(system=system, message=message)
        return {"reply": "One shot.", "steps": [{
            "tool": "generate", "workflow": "video/@seedance_2_5", "name": "Rain", "prompt": "The girl walks home in the rain.",
            "uses": [{"item": 0, "asset": meera, "slot": "ref_1"}, {"item": 0, "asset": meera, "slot": "ref_2"},   # once is enough
                     {"item": 0, "asset": 999, "slot": "ref_3"},                                                   # not in the book
                     {"item": harbour, "asset": 0, "slot": "ref_4"}]}]}   # a picture of the project, not attached

    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    plan = client.post("/api/agent/plan", json={"instruction": "/short-film a short film: Meera walks home in the rain", "project_id": film(client)}).json()
    step = plan["steps"][0]
    assert [(u.get("asset"), u["id"], u["name"], u["slot"]) for u in step["uses"]] == [
        (meera, 0, "Meera", "ref_1"), (None, harbour, "Harbour", "ref_4")]
    # The model was given the book, with the user's note, and the skill for a film.
    assert '"name": "Meera"' in asked["message"] and "Use her for every shot of the girl." in asked["message"]
    assert '"asset": %d' % cafe in asked["message"] and "A harbour at dawn." in asked["message"]
    assert "skill short-film" in asked["message"]
    assert "NeuralCore (the project's memory)" in asked["system"]

    # On Approve the browser sends the saved asset by its id, which the job takes as it is.
    assert client.post("/api/jobs", data={"settings": '{"workflow": "video/@seedance_2_5", "refs": {"ref_1": {"asset_id": 999}}}'}).status_code == 400


def test_an_asset_saved_from_the_library_keeps_what_the_model_saw_and_notes_can_be_changed(client):
    me = register(client)
    item = library_item(client, me["id"], "Harbour", about="A harbour at dawn.", project=film(client))
    client.app.state.db.run("UPDATE generations SET filename = 'harbour.png' WHERE id = ?", (item,))
    folder = client.app.state.outputs.folder(me["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "harbour.png").write_bytes(PNG)
    asset = client.post("/api/kit", json={"item": item, "name": "Harbour", "type": "location", "project_id": film(client)}).json()["id"]
    client.put("/api/kit/%d" % asset, json={"use_note": "For the opening."})
    saved = client.get("/api/kit?project=%d" % film(client)).json()["entries"][0]
    assert (saved["about"], saved["use_note"]) == ("A harbour at dawn.", "For the opening.")
    client.put("/api/kit/%d" % asset, json={"about": "  A small harbour,\n at dawn. ", "use_note": "x" * 900})
    saved = client.get("/api/kit?project=%d" % film(client)).json()["entries"][0]
    assert saved["about"] == "A small harbour, at dawn." and len(saved["use_note"]) == 600


def test_only_the_user_picks_a_skill_and_a_video_gets_the_default(tmp_path):
    # a message's words never pick a skill: only the ones the user chose are given, in their order; the one exception is
    # the director, which comes on its own (marked "auto") for multi-shot story work (skills.wants_directing)
    assert [(s["id"], s.get("auto")) for s in skills.pick("a short film: a girl finds a stray dog in the rain")] == [("shot-planner", True)]
    assert skills.pick("make a 20 second Reel ad for our coffee product") == []
    assert [s["id"] for s in skills.pick("x", force=["product-ad", "no-such-skill", "product-ad"])] == ["product-ad"]
    # a message asking for a video is one for the default skill; an edit of a video already there is not
    assert skills.DEFAULT == "story-to-screen" and skills.find(skills.DEFAULT)
    for said in ("make a video from this script and audio", "turn my script into a film", "create a 30 second reel for my cafe",
                 "i want a short film about two brothers", "script to video", "here is my script, make it into a movie"):
        assert skills.wants_video(said), said
    for said in ("make the video shorter", "add music to this video", "cut this video in half", "make a picture of a cat",
                 "hello, what can you do?", "make a character sheet of maya"):
        assert not skills.wants_video(said), said
    # a habit or a past film is no request; one clip (at most 15 s, "a clip") is made without the skill...
    for said in ("I always make Reels", "we usually create short films for clients", "I made a film last week",
                 "a music video is hard to make", "make a 5 second video of a cat", "generate a 10s clip of rain on a window",
                 "make a quick clip of a dog running", "i like films about rain"):
        assert not skills.wants_video(said), said
    # a video of words and shapes is the agent's own pages (HyperFrames), not a film made from a script
    for said in ("create a cool video using hyperframes", "make a motion graphics video about our app",
                 "create a kinetic typography video for this quote", "make a lyric video for my song"):
        assert not skills.wants_video(said), said
    # ...unless it is more than one clip, or a script or a sound is attached
    for said in ("make a 30 second film about two brothers", "make a 10 s video of the 3 scenes of my story",
                 "can you make a reel for my cafe?", "i'd like a short film about rain"):
        assert skills.wants_video(said), said
    assert skills.wants_video("make a 5 second video", attached=["audio"]) and skills.wants_video("turn @1 into a 10 s video", attached=["text"])
    assert not skills.wants_video("make a 5 second video", attached=["image"])
    # A short follow-up is about the same work as the message before it.
    assert skills.wants_video("yes, portrait", [{"instruction": "make a video of my dog"}])
    # Every skill that ships can be read and has words the user can name it by.
    shipped = skills.load()
    assert {s["id"] for s in shipped} >= {"short-film", "product-ad", "character-sheet", "social-video"}
    # (a skill an admin adds may have no trigger words: it then runs only when named with /command)
    assert all(s["text"] and s["words"].pattern != "(?!)" for s in shipped if s["id"] in ("short-film", "product-ad", "character-sheet", "social-video"))
    # A skill whose words can't be read is left out.
    (tmp_path / "broken.md").write_text("id: broken\nwords: (unclosed\n---\nText.", encoding="utf-8")
    (tmp_path / "fine.md").write_text("id: fine\ntitle: Fine\nwords: \\bfine\\b\n---\nDo it well.", encoding="utf-8")
    assert [s["id"] for s in skills.load(tmp_path)] == ["fine"]
    assert "Fine (skill fine v1):\nDo it well." == skills.guide(skills.pick("a fine thing", folder=tmp_path, force=["fine"]))


def test_a_file_dropped_into_a_job_is_kept_once_as_an_upload_of_its_project(client, monkeypatch):
    me = register(client)
    project = client.post("/api/projects", json={"name": "Rain"}).json()["id"]
    settings = {"workflow": "video/@seedance_2_5", "values": {"2:value": "She waves."}, "project_id": project}
    for _ in range(2):   # the same file twice is kept once
        made = client.post("/api/jobs", data={"settings": json.dumps(settings)}, files={"ref:ref_1": ("meera_face.png", PNG, "image/png")})
        assert made.status_code == 200
    shown = client.get("/api/kit?project=%d" % project).json()["entries"]
    # typed by its slot: a model's numbered reference picture says nothing of what it holds
    assert [(u["name"], u["type"], u["origin"]) for u in shown] == [("meera face", "other", "upload")]
    assert client.get("/api/kit").json()["entries"] == []   # only in its own project
    upload_id = shown[0]["id"]
    assert client.get("/api/kit/%d/file" % upload_id).content == PNG
    # The agent knows it by name in that project.
    book = memory.book_for_model(memory.book(client.app.state.db, me["id"], project))
    assert book[0]["asset"] == upload_id and book[0]["type"] == "other"
    # A deleted project takes its NeuralCore with it: nothing is left outside a project.
    second = client.post("/api/jobs", data={"settings": json.dumps(settings)}, files={"ref:ref_1": ("cafe.png", PNG + b"cafe", "image/png")})
    assert second.status_code == 200
    client.delete("/api/projects/%d" % project)
    assert client.get("/api/kit").json()["entries"] == [] and not client.app.state.db.one("SELECT 1 FROM assets")
    assert client.get("/api/kit/%d/file" % upload_id).status_code == 404


def test_there_are_no_project_notes(client, monkeypatch):
    register(client)
    asked = []

    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        asked.append((system, message))
        return {"reply": "Noted.", "steps": []}

    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    plan = client.post("/api/agent/plan", json={"instruction": "a short film: a girl finds a stray dog in the rain"}).json()
    assert "remembered" not in plan and "Project notes" not in asked[-1][0] and "Project notes" not in asked[-1][1]
    assert set(client.get("/api/memory").json()) == {"assets", "uploads", "skills"}   # the tab lists assets and uploads only
    assert client.put("/api/memory/notes", json={"key": "style", "text": "x"}).status_code in (404, 405)


def test_the_book_gives_the_latest_items_in_full_and_older_ones_by_name(client):
    me = register(client)
    for number in range(memory.BOOK_FULL_ITEMS + 3):
        client.app.state.db.run(
            "INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, created, about) "
            "VALUES (?, 'x/y', 'image', ?, 'missing', '', '{}', '{}', ?, 'A long description of what this picture shows.')",
            (me["id"], "Shot %d" % number, number))
    book = memory.book_for_model(memory.book(client.app.state.db, me["id"], 0))
    assert len(book) == memory.BOOK_FULL_ITEMS + 3 and book[0]["name"] == "Shot %d" % (memory.BOOK_FULL_ITEMS + 2)
    assert "type" in book[0] and "type" not in book[-1] and set(book[-1]) == {"item", "name", "kind", "shows"}


def test_what_a_step_makes_for_reuse_is_kept_in_shared_memory_under_its_name(client, tmp_path):
    """A character the agent made ("keep" on its step) becomes a saved asset when the job records it, so another agent
    tab or project finds "Maya" by name. A retake replaces it; an asset the user saved is never replaced."""
    me = register(client)
    jobs, db = client.app.state.jobs, client.app.state.db
    assert memory.clean_keep({"as": "location", "name": "  the   cafe "}, "image") == {"tag": "background", "name": "the cafe"}
    assert memory.clean_keep({"as": "voice", "name": "Maya"}, "image") is None   # a voice is a sound, not a picture
    assert memory.clean_keep({"as": "", "name": ""}) is None

    def made(name, keep):
        target = tmp_path / (name + ".png")
        target.write_bytes(PNG)
        job = {"id": name, "user_id": me["id"], "workflow": "image/z", "name": name, "summary": "", "started": 0,
               "project_id": film(client), "settings": {"prompt": "a woman", "keep": keep}}
        a_job(client.app.state.db, name, me["id"], "image/z")
        jobs._record(job, "image", target, {})

    made("maya1", {"tag": "character", "name": "Maya"})
    made("plain", None)   # an ordinary picture is only in the library
    shown = client.get("/api/memory?project=%d" % film(client)).json()["assets"]
    assert [(a["name"], a["type"]) for a in shown] == [("Maya", "character")]
    first = db.one("SELECT id, filename, made_from FROM assets WHERE name = 'Maya'")
    assert first["made_from"] and (client.app.state.assets_dir / str(me["id"]) / first["filename"]).is_file()

    made("maya2", {"tag": "character", "name": "maya"})   # a retake under the same name: the same asset, the new picture
    again = db.all("SELECT id, filename FROM assets WHERE lower(name) = 'maya'")
    assert len(again) == 1 and again[0]["id"] == first["id"] and again[0]["filename"] != first["filename"]
    assert not (client.app.state.assets_dir / str(me["id"]) / first["filename"]).exists()

    saved = save_asset(client, "Liam", "character")   # saved by the user: a step named Liam adds its own, never replaces it
    made("liam", {"tag": "character", "name": "Liam"})
    assert len(db.all("SELECT id FROM assets WHERE name = 'Liam'")) == 2 and db.one("SELECT 1 FROM assets WHERE id = ?", (saved,))
    book = memory.book_for_model(memory.book(db, me["id"], film(client)))
    assert {e["name"] for e in book if e.get("type") == "character"} == {"Maya", "Liam"}


def test_the_always_on_cast_fills_a_models_numbered_reference_pictures_in_order(client):
    """A provider's model names its reference pictures "REFERENCE 1", "REFERENCE 2" ...: the cast goes into them in
    order, characters first, and never into its first frame, last frame or reference video."""
    import asyncio
    from scene import kit
    from scene.comfy import workflows
    schema = workflows.describe(asyncio.run(client.app.state.catalog.load("video/@seedance_2_5")))
    on = [{"id": 3, "name": "Cafe", "tag": "background", "kind": "image"}, {"id": 1, "name": "Maya", "tag": "character", "kind": "image"},
          {"id": 2, "name": "Liam", "tag": "character", "kind": "image"}]
    filled = kit.fills(schema, on)
    assert [(f["slot"], f["name"]) for f in filled] == [("ref_1", "Maya"), ("ref_2", "Liam"), ("ref_3", "Cafe")]
    # a slot already given a file is left as it is, and the rest follow without a gap
    assert [(f["slot"], f["name"]) for f in kit.fills(schema, on, taken={"ref_1"})] == [("ref_2", "Maya"), ("ref_3", "Liam"), ("ref_4", "Cafe")]

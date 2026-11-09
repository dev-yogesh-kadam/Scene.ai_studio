"""A reference kept for reuse is checked as a reference: sharp, plain, one subject. One that fails says so in NeuralCore,
so the agent makes it again before shots lean on it."""

import asyncio
import json

from scene import kit, memory, review
from test_agent_review import FAILED, PNG, model_says
from test_api import register


def sheet(client, user_id, project, keep):
    """A picture the agent made to keep, in the project's library."""
    folder = client.app.state.outputs.folder(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "sheet.png").write_bytes(PNG)
    settings = {"workflow": "image/image_t2i_flux2_klein_9b", "prompt": "Character reference sheet of Meera.", "keep": keep}
    return client.app.state.db.run(
        "INSERT INTO generations (user_id, project_id, workflow, kind, name, filename, summary, settings, context, seconds, size, created) "
        "VALUES (?, ?, 'image/image_t2i_flux2_klein_9b', 'image', 'Meera', 'sheet.png', '', ?, '{}', 1, 1, 1)",
        (user_id, project, json.dumps(settings)))


def test_a_kept_sheet_is_reviewed_as_a_reference(client, monkeypatch):
    me = register(client)
    film = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    state = client.app.state
    seen = {}
    model_says(monkeypatch, client, FAILED, seen)
    item = state.db.one("SELECT * FROM generations WHERE id = ?", (sheet(client, me["id"], film, {"tag": "character", "name": "Meera"}),))
    asyncio.run(review.review_item(state, me["id"], dict(item), ""))
    assert "kept as a reference" in seen["prompt"] and "head to toe" in seen["prompt"]
    # a shot that is not kept is reviewed as before
    plain = state.db.one("SELECT * FROM generations WHERE id = ?", (sheet(client, me["id"], film, None),))
    asyncio.run(review.review_item(state, me["id"], dict(plain), ""))
    assert "kept as a reference" not in seen["prompt"]
    assert set(review.SHEET_CHECKS) <= set(memory.KEEP_AS.values())


def test_a_sheet_that_failed_says_so_in_neuralcore(client):
    me = register(client)
    film = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    state = client.app.state
    item = sheet(client, me["id"], film, {"tag": "character", "name": "Meera"})
    folder = state.assets_dir / str(me["id"])
    memory.keep_made(state.db, folder, me["id"], item, state.outputs.folder(me["id"]) / "sheet.png", "image", {"as": "character", "name": "Meera"})

    def entry():
        row = next(r for r in kit.entries(state.db, me["id"], film) if r["name"] == "Meera")
        return memory._asset_entry(row)
    assert "review" not in entry()   # not checked yet
    state.db.run("UPDATE generations SET review = ? WHERE id = ?", (json.dumps(review.verdict_from(FAILED)), item))
    assert entry()["review"].startswith("Failed the review")
    state.db.run("UPDATE generations SET review = ? WHERE id = ?", (json.dumps({"passed": True, "checks": []}), item))
    assert "review" not in entry()   # a sheet that passed needs no word

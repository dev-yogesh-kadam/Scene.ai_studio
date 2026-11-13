"""The console's Servers: ComfyUI servers are added, changed and removed while the app runs, and a waiting render goes
to one that can do it and is free (balancer.py). The model servers and APIs of before (Ollama, Kimi, Gemini) are gone: the agent uses only Claude."""

import asyncio
import time

from test_api import console, register


def test_servers_are_added_changed_and_removed_in_the_console(client):
    register(client)
    desk = console(client)
    listed = desk.get("/api/admin/endpoints").json()
    assert listed["kinds"] == {"comfy": "ComfyUI", "langfuse": "Langfuse"}
    assert [(e["kind"], e["url"]) for e in listed["endpoints"]] == [("comfy", "http://127.0.0.1:9")]   # config.json's
    desk.post("/api/admin/endpoints", json={"kind": "comfy", "name": "", "url": " 127.0.0.8188 "})   # nothing is refused
    loose = client.app.state.db.one("SELECT * FROM endpoints ORDER BY id DESC LIMIT 1")
    assert (loose["name"], loose["url"]) == ("ComfyUI", "http://127.0.0.8188")
    desk.put("/api/admin/endpoints/%d" % loose["id"], json={"active": False})
    assert not client.app.state.db.one("SELECT active FROM endpoints WHERE id = ?", (loose["id"],))["active"]
    desk.delete("/api/admin/endpoints/%d" % loose["id"])
    desk.post("/api/admin/endpoints", json={"kind": "ollama", "name": "Kaggle", "url": "https://kaggle.example/"})
    assert client.app.state.db.one("SELECT kind FROM endpoints ORDER BY id DESC LIMIT 1")["kind"] == "comfy"   # only ComfyUI


def test_the_model_servers_of_before_are_taken_out(client):
    """Migration 0008 takes them out (as the app's start did before it) and its check keeps any other kind out."""
    import pytest
    from scene import endpoints
    db = client.app.state.db
    with pytest.raises(Exception, match="endpoints_kind_known"):
        db.run("INSERT INTO endpoints (kind, name, url, api_key, models, active, created) VALUES ('openai', 'Kimi', 'https://x', 'k', '', 1, ?)",
               (time.time(),))
    endpoints.seed(db, client.app.state.settings)
    assert [r["kind"] for r in db.all("SELECT kind FROM endpoints")] == ["comfy"]


def test_a_render_goes_to_a_server_that_is_free(client):
    """The load balancer (test_balancer.py has the rest): a ComfyUI server runs one render at a time."""
    register(client)
    console(client).post("/api/admin/endpoints", json={"kind": "comfy", "name": "Zoro 2", "url": "http://127.0.0.1:8"})
    pool = client.app.state.comfy_pool
    pool.nodes = {s["url"]: (None, time.time()) for s in pool.servers()}   # nodes not known: not asked of anyone

    async def answers(url):
        return True

    def place():
        return asyncio.run(pool.place("image/image_t2i_flux3_klein", frozenset({"KSampler"}), answers))
    first, _, _ = place()
    assert first["url"] == "http://127.0.0.1:9"   # the main one first
    pool.take("http://127.0.0.1:9", "job1")
    second, _, _ = place()
    assert second["name"] == "Zoro 2" and pool.client(second["url"]) is not client.app.state.comfy
    pool.take("http://127.0.0.1:8", "job2")
    assert place() == (None, True, "")   # all busy: it waits for one
    pool.busy.clear()

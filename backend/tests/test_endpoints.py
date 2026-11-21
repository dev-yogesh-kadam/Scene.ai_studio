"""The console's Servers: Langfuse alone, added, changed and removed while the app runs. The models come from the
providers (Servers & APIs → Providers): a ComfyUI server is refused, and the model servers and APIs of before (ComfyUI,
Ollama, Kimi, Gemini) are taken out."""

import time

from test_api import console, register


def test_langfuse_is_added_changed_and_removed_in_the_console(client):
    register(client)
    desk = console(client)
    listed = desk.get("/api/admin/endpoints").json()
    assert listed == {"kinds": {"langfuse": "Langfuse"}, "endpoints": []}   # no render server any more
    assert desk.post("/api/admin/endpoints", json={"kind": "langfuse", "name": "", "url": " 127.0.0.1:3000 "}).status_code == 200
    loose = client.app.state.db.one("SELECT * FROM endpoints ORDER BY id DESC LIMIT 1")
    assert (loose["kind"], loose["name"], loose["url"]) == ("langfuse", "Langfuse", "http://127.0.0.1:3000")   # tidied, not refused
    desk.put("/api/admin/endpoints/%d" % loose["id"], json={"active": False})
    assert not client.app.state.db.one("SELECT active FROM endpoints WHERE id = ?", (loose["id"],))["active"]
    desk.delete("/api/admin/endpoints/%d" % loose["id"])
    assert client.app.state.db.one("SELECT id FROM endpoints") is None


def test_a_comfyui_server_or_another_kind_is_refused(client):
    register(client)
    desk = console(client)
    for kind in ("comfy", "ollama"):
        refused = desk.post("/api/admin/endpoints", json={"kind": kind, "name": "Zoro", "url": "http://127.0.0.1:8188"})
        assert refused.status_code == 400 and "Providers" in refused.json()["detail"], kind
    desk.post("/api/admin/endpoints", json={"kind": "langfuse", "url": "http://127.0.0.1:3000"})
    langfuse = client.app.state.db.one("SELECT id FROM endpoints")["id"]
    assert desk.put("/api/admin/endpoints/%d" % langfuse, json={"kind": "comfy"}).status_code == 400   # nor made one later
    assert client.app.state.db.one("SELECT kind FROM endpoints")["kind"] == "langfuse"


def test_the_servers_of_before_are_taken_out(client):
    """Migration 0008 takes the model APIs out and its check keeps any other kind out; the start takes out a ComfyUI
    server still listed (migration 0019 took them out)."""
    import pytest
    from scene import endpoints
    db = client.app.state.db
    with pytest.raises(Exception, match="endpoints_kind_known"):
        db.run("INSERT INTO endpoints (kind, name, url, api_key, models, active, created) VALUES ('openai', 'Kimi', 'https://x', 'k', '', 1, ?)",
               (time.time(),))
    db.run("INSERT INTO endpoints (kind, name, url, api_key, models, active, created) VALUES ('comfy', 'Zoro', 'http://zoro:8188', '', '', 1, ?)",
           (time.time(),))
    db.run("INSERT INTO endpoints (kind, name, url, api_key, models, active, created) VALUES ('langfuse', 'Langfuse', 'http://x', '', '', 1, ?)",
           (time.time(),))
    endpoints.seed(db, client.app.state.settings)
    assert [r["kind"] for r in db.all("SELECT kind FROM endpoints")] == ["langfuse"]

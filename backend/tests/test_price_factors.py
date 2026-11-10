"""Prices by what was chosen: a resolution and a quality each multiply the price (credits.FACTORS), set for the studio
in the console and, where one needs it, for a single workflow."""

import json
import time

from test_api import JOB, console, post_job, register


def quote(client, **changes):
    return client.post("/api/estimate", json={**JOB, **changes}).json()


def test_the_price_follows_the_resolution_and_quality_chosen(client):
    register(client)
    credits = client.app.state.credits
    assert credits.cost("video/x", 5) == 100                                          # nothing chosen: the rate itself
    assert credits.cost("video/x", 5, {"resolution": 480, "quality": "draft"}) == 30  # 20/s x 5 s x 0.6 x 0.5
    assert credits.cost("video/x", 5, {"resolution": 768, "quality": "final"}) == 100  # 768p is priced as 720p
    assert credits.cost("video/x", 5, {"resolution": 1080, "quality": "final"}) == 200
    assert credits.cost("image/x", None, {"resolution": 1080, "quality": "draft"}) == 20   # a picture: its quality only
    assert credits.cost("video/x", 5, {"resolution": 1080, "quality": "medium"}) == 160
    low = quote(client, options={"quality": "low"}, values={"100:value": "She waves.", "501:value": 480})   # H3 All In One: its own RESOLUTION
    high = quote(client, options={"quality": "high"}, values={"100:value": "She waves.", "501:value": 1080})
    assert low["credits"] < high["credits"]
    assert low["choices"]["resolution"]["1080"] > low["choices"]["resolution"]["480"] == low["credits"]
    assert set(low["choices"]["quality"]) >= {"low", "high"}


def test_admins_set_the_factors_for_the_studio_and_for_one_workflow(client):
    register(client)
    desk = console(client)
    found = desk.get("/api/admin/pricing/factors").json()
    assert found["factors"]["resolution"]["1080"] == 2.0 and found["defaults"]["quality"]["draft"] == 0.5
    assert desk.put("/api/admin/pricing/factors", json={"resolution": {"1080": 30}}).status_code == 400
    changed = desk.put("/api/admin/pricing/factors", json={"resolution": {"1080": 3}, "quality": {"draft": 0.4}}).json()
    assert changed["factors"]["resolution"]["1080"] == 3 and changed["factors"]["resolution"]["480"] == 0.6
    assert client.app.state.credits.cost("video/x", 5, {"resolution": 1080}) == 300
    own = desk.put("/api/admin/pricing/workflow/factors", json={"workflow": "video/h3_all_in_one", "resolution": {"1080": 1.5}}).json()
    assert own["factors"]["resolution"]["1080"] == 1.5 and own["factors"]["quality"]["draft"] == 0.4
    assert client.app.state.credits.cost("video/h3_all_in_one", 5, {"resolution": 1080}) == 150
    assert client.app.state.credits.cost("video/other", 5, {"resolution": 1080}) == 300
    listed = next(w for w in desk.get("/api/admin/pricing").json()["workflows"] if w["id"] == "video/h3_all_in_one")
    assert listed["own_factors"]["resolution"] == {"1080": 1.5}
    desk.put("/api/admin/pricing/workflow/factors", json={"workflow": "video/h3_all_in_one"})
    assert client.app.state.credits.cost("video/h3_all_in_one", 5, {"resolution": 1080}) == 300
    assert "Changed the price factors" in [a["action"] for a in desk.get("/api/admin/audit").json()["entries"]]


def test_a_job_is_charged_at_its_chosen_price_and_factors_are_suggested_from_render_times(client):
    register(client)
    desk = console(client)
    desk.put("/api/admin/queue", json={"paused": True})
    before = client.get("/api/auth/me").json()["credits"]
    job = post_job(client, options={"mode": "fast", "quality": "low"}, resolution=480).json()
    assert job["credits"] == quote(client, options={"mode": "fast", "quality": "low"}, resolution=480)["credits"]
    assert client.get("/api/auth/me").json()["credits"] == before - job["credits"]
    db, now = client.app.state.db, time.time()
    for resolution, quality, took in ((720, "high", 100), (720, "high", 140), (1080, "high", 360), (720, "low", 72)):
        db.run("INSERT INTO jobs (id, user_id, name, workflow, kind, settings, summary, status, created, started, finished, seconds_requested) "
               "VALUES (?, 1, 'x', 'video/h3_all_in_one', 'video', ?, '', 'done', ?, ?, ?, 5)",
               ("t{}{}{}".format(resolution, quality, took), json.dumps({"resolution": resolution, "options": {"quality": quality}}), now, now - took, now))
    found = desk.get("/api/admin/pricing/factors").json()
    assert found["suggested"]["resolution"]["1080"] == round(360 / ((100 + 140 + 72) / 3), 2)
    assert found["suggested"]["quality"]["low"] == round(72 / ((100 + 140 + 360) / 3), 2)
    assert found["samples"]["resolution"]["720"] == 3


def test_an_estimate_prices_every_choice_with_its_rates_read_once(client, monkeypatch):
    """An estimate priced each other resolution and quality beside the one picked, each reading the six rates, the
    studio's factors and the workflow's pricing again (9 queries a price, about 70 a step), and read the last 500 runs
    every time: a plan of eight steps sent ~700 queries. The prices are the same."""
    register(client)
    db, credits = client.app.state.db, client.app.state.credits
    first = quote(client)
    assert credits.costs("video/x", 5, [None, {"resolution": 1080, "quality": "final"}, {"resolution": 480, "quality": "draft"}]) == [100, 200, 30]
    asked = []
    real = db._execute
    monkeypatch.setattr(db, "_execute", lambda sql, params=(), *a, **k: asked.append(sql) or real(sql, params, *a, **k))
    again = quote(client)
    assert again["credits"] == first["credits"] and again["choices"] == first["choices"] and len(first["choices"]["resolution"]) > 1
    settings = [q for q in asked if "FROM settings" in q]
    assert len(settings) <= 6 and not any("FROM generations ORDER BY created DESC LIMIT 500" in q for q in asked)   # it was 50+, and the 500 runs
    assert len(asked) < 25
    post_job(client)   # something new is made (or queued): the runs are read again for the next estimate
    a_run = client.app.state.db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, seconds, created) "
                                    "VALUES ((SELECT MIN(id) FROM users), 'video/h3_all_in_one', 'video', 'r', 'r.mp4', '{}', '{}', 30, ?)", (time.time(),))
    asked.clear()
    quote(client)
    assert a_run and any("FROM generations ORDER BY created DESC LIMIT 500" in q for q in asked)

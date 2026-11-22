"""The admin console's Workflows: who a model is offered to (versions.py), the "new models start for admins only"
switch (providers/workflows.ProviderWorkflows._hold_new), and test runs.

(The versions of the ComfyUI workflow files the render PC handed over, what changed between them and what they needed
that the render server lacked went with those files on 18 November.)"""

import json

import studio_models
from scene.providers import registry
from test_api import console, post_job, register

BOB = {"email": "bob@example.com", "password": "another one"}
SEEDANCE = "video/@seedance_2_5"


def ids(client):
    return [w["id"] for w in client.get("/api/workflows").json()["workflows"]]


def test_a_workflow_can_be_tried_by_admins_before_users_see_it(client):
    register(client)
    desk = console(client)
    report = desk.get("/api/admin/workflows").json()
    seedance = next(w for w in report["workflows"] if w["id"] == SEEDANCE)
    assert seedance["audience"] == "everyone" and seedance["example"] > 0 and seedance["provider"] is True
    assert desk.put("/api/admin/workflows/audience", json={"workflow": SEEDANCE, "audience": "nobody"}).status_code == 400
    assert desk.put("/api/admin/workflows/audience", json={"workflow": "video/h3_all_in_one", "audience": "admins"}).status_code == 404
    assert desk.put("/api/admin/workflows/audience", json={"workflow": SEEDANCE, "audience": "admins"}).json()["audience"] == "admins"
    assert SEEDANCE in ids(client)                                # the admin sees it
    assert post_job(client).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json=BOB)
    assert SEEDANCE not in ids(client)                            # a user does not, and can't use it
    assert post_job(client).status_code == 400
    desk.put("/api/admin/workflows/audience", json={"workflow": SEEDANCE, "audience": "everyone"})
    assert SEEDANCE in ids(client)
    desk.put("/api/admin/workflows/audience", json={"workflow": SEEDANCE, "audience": "off"})
    assert SEEDANCE not in ids(client)
    pricing = next(w for w in desk.get("/api/admin/pricing").json()["workflows"] if w["id"] == SEEDANCE)
    assert pricing["enabled"] is False and pricing["admins_only"] is False
    assert desk.put("/api/admin/workflows/settings", json={"new_admins_only": True}).json() == {"new_admins_only": True}
    assert desk.get("/api/admin/workflows").json()["new_admins_only"] is True


def offer_a_new_model(client, model_id):
    """The provider's key now offers one more model (its models read again, as every 10 minutes)."""
    db = client.app.state.db
    key = db.one("SELECT k.id, k.provider_id FROM provider_keys k JOIN providers p ON p.id = k.provider_id "
                 "WHERE p.kind = 'scene_provider_v1' ORDER BY k.id LIMIT 1")   # the test provider's (not On this PC's)
    model = dict(next(m for m in studio_models.MODELS if m["id"] == "seedream_5"), id=model_id, name="Seedream 6")
    client.provider.models.append(model)
    registry.save_models(db, key["provider_id"], key["id"], client.provider.models)
    client.app.state.catalog.providers.read_at = 0.0


def test_a_new_model_starts_for_admins_only_when_the_console_says_so(client):
    register(client)
    desk = console(client)
    assert "image/@seedream_5" in ids(client)   # the first look learns what is offered: nothing is held back
    desk.put("/api/admin/workflows/settings", json={"new_admins_only": True})
    offer_a_new_model(client, "seedream_6")
    assert "image/@seedream_6" in ids(client)   # the admin sees it at once
    audience = {w["id"]: w["audience"] for w in desk.get("/api/admin/workflows").json()["workflows"]}
    assert audience["image/@seedream_6"] == "admins" and audience["image/@seedream_5"] == "everyone"
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json=BOB)
    assert "image/@seedream_6" not in ids(client) and "image/@seedream_5" in ids(client)
    desk.put("/api/admin/workflows/audience", json={"workflow": "image/@seedream_6", "audience": "everyone"})
    assert "image/@seedream_6" in ids(client)


def test_with_the_switch_off_a_new_model_is_offered_to_everyone(client):
    register(client)
    assert "image/@seedream_5" in ids(client)
    offer_a_new_model(client, "seedream_6")
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json=BOB)
    assert "image/@seedream_6" in ids(client)


def test_a_test_run_is_free_first_in_the_queue_and_runs_under_maintenance(client):
    me = register(client)
    desk = console(client)
    desk.put("/api/admin/queue", json={"paused": True})
    post_job(client)
    credits = client.get("/api/auth/me").json()["credits"]
    desk.put("/api/admin/maintenance", json={"on": True})
    test = desk.post("/api/admin/workflows/test", json={"workflow": SEEDANCE})
    assert test.status_code == 200 and test.json()["name"].startswith("Test · ")
    job = client.app.state.db.one("SELECT * FROM jobs WHERE id = ?", (test.json()["id"],))
    assert job["user_id"] == me["id"] and job["cost"] == 0 and job["priority"] == 100 and job["status"] == "queued"
    assert json.loads(job["settings"])["test"] is True and json.loads(job["settings"])["prompt"]
    assert client.get("/api/auth/me").json()["credits"] == credits
    waiting = desk.get("/api/admin/overview").json()["queue"]["waiting"]
    assert waiting[0]["id"] == test.json()["id"]                     # ahead of the job that was there first
    assert desk.post("/api/admin/workflows/test", json={"workflow": "video/nothing"}).status_code == 400
    assert desk.post("/api/admin/workflows/test", json={"workflow": "video/@lip_sync"}).status_code == 400   # it needs files
    assert "Test run of a workflow" in [a["action"] for a in desk.get("/api/admin/audit").json()["entries"]]

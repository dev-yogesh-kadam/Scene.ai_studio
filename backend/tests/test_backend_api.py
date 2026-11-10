"""The API's hardening pass (November 2026): routes that had no test, object-level checks between two users, input
checks, clean JSON errors and paging."""

import json

import pytest

from test_mobile_api import ADA, item, signed_in
from test_plans import step

BOB = {"email": "bob@example.com", "password": "correct horse"}


# ---------------------------------------------------------------- the share page's look (CSP: no inline <style>)

def test_the_share_page_takes_its_look_from_a_file_the_policy_allows(client):
    ada = signed_in(client)
    made = item(client, ada["id"], "Fox")
    link = client.post("/api/library/{}/share".format(made)).json()
    client.cookies.clear()
    page = client.get(link["path"])
    assert page.status_code == 200 and "<style" not in page.text and 'style="' not in page.text
    assert '<link rel="stylesheet" href="/s/share.css">' in page.text
    assert "style-src 'self'" in page.headers["content-security-policy"]   # the policy that dropped the inline <style>
    css = client.get("/s/share.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert "video,img{" in css.text and "{{" not in css.text


# ---------------------------------------------------------------- one user never reaches another's things

def _adas_things(client):
    """Ada's project, an item in it, a NeuralCore entry, a plan, a canvas, an agent tab, a run's state, a share link
    and a job; then Bob signs in, a stranger to all of it."""
    ada = signed_in(client)
    project = client.post("/api/projects", json={"name": "Ada's film"}).json()["id"]
    made = item(client, ada["id"], "Fox")
    client.app.state.db.run("UPDATE generations SET project_id = ? WHERE id = ?", (project, made))
    entry = client.post("/api/kit", json={"project_id": project, "text": "Fade in.", "name": "Script"}).json()["id"]
    plan = client.post("/api/agent/plans", json={"steps": [step("one")]}).json()["id"]
    assert client.put("/api/boards/canvas", json={"project": project, "data": {"ada": 1}}).json() == {"ok": True}
    assert client.put("/api/boards/agent-t1", json={"project": project, "data": {"runs": [{"instruction": "ada's"}]}}).json() == {"ok": True}
    assert client.put("/api/runs/run1/state", json={"path": "/secret", "value": "ada's"}).status_code == 200
    assert client.post("/api/library/{}/share".format(made)).status_code == 200
    job = client.post("/api/jobs", data={"settings": json.dumps({"workflow": "video/h3_all_in_one",
                                                                 "values": {"100:value": "She waves."}})}).json()["id"]
    signed_in(client, BOB)
    return {"project": project, "item": made, "entry": entry, "plan": plan, "job": job}


def test_a_stranger_can_neither_read_nor_change_anything_of_anothers(client):
    t = _adas_things(client)
    p, i, e, plan, job = t["project"], t["item"], t["entry"], t["plan"], t["job"]
    refused = [
        ("get", "/api/projects/{}".format(p)), ("put", "/api/projects/{}".format(p), {"name": "Bob's now"}),
        ("delete", "/api/projects/{}".format(p)), ("get", "/api/projects/{}/members".format(p)),
        ("post", "/api/projects/{}/members".format(p), {"people": [{"email": BOB["email"], "role": "manager"}]}),
        ("get", "/api/projects/{}/analytics".format(p)), ("get", "/api/projects/{}/analytics.csv".format(p)),
        ("post", "/api/projects/{}/duplicate".format(p), {}), ("put", "/api/projects/{}/canvas".format(p), {"name": "x"}),
        ("get", "/api/library/{}".format(i)), ("get", "/api/library/{}/file".format(i)), ("get", "/api/library/{}/poster".format(i)),
        ("put", "/api/library/{}".format(i), {"name": "Bob's now"}), ("delete", "/api/library/{}".format(i)),
        ("post", "/api/library/{}/reference".format(i)), ("post", "/api/library/{}/share".format(i)),
        ("delete", "/api/library/{}/share".format(i)), ("get", "/api/mobile/library/{}".format(i)),
        ("get", "/api/library?project={}".format(p)), ("get", "/api/mobile/library?project={}".format(p)),
        ("get", "/api/mobile/modules/{}".format(p)), ("get", "/api/library/placement?project={}".format(p)),
        ("get", "/api/kit?project={}".format(p)), ("get", "/api/kit/{}/file".format(e)),
        ("put", "/api/kit/{}".format(e), {"name": "Bob's now"}), ("delete", "/api/kit/{}".format(e)),
        ("post", "/api/kit/order", {"project_id": p, "ids": [e]}),
        ("get", "/api/agent/plans/{}".format(plan)), ("post", "/api/agent/plans/{}/approve".format(plan)),
        ("post", "/api/agent/plans/{}/stop".format(plan)), ("post", "/api/agent/plans/{}/resume".format(plan)),
        ("post", "/api/agent/plans/{}/choose".format(plan), {"step": 0, "item": i}),
        ("get", "/api/boards/canvas?project={}".format(p)), ("put", "/api/boards/canvas", {"project": p, "data": {"bob": 1}}),
        ("get", "/api/boards/agent-t1?project={}".format(p)), ("delete", "/api/boards/agent-t1?project={}".format(p)),
        ("get", "/api/core/memory?project={}".format(p)), ("put", "/api/core/state", {"project_id": p, "path": "/x", "value": 1}),
        ("get", "/api/cast?project={}".format(p)), ("get", "/api/memory?project={}".format(p)),
        ("delete", "/api/jobs/{}".format(job)), ("post", "/api/jobs/{}/retry".format(job)),
    ]
    for method, path, *body in refused:
        answer = getattr(client, method)(path, **({"json": body[0]} if body else {}))
        assert answer.status_code in (403, 404), (method, path, answer.status_code, answer.text[:200])
        assert "application/json" in answer.headers["content-type"], (method, path)
    # what Bob's own lists and his own run of the same name hold: nothing of Ada's
    assert client.get("/api/agent/plans").json()["plans"] == []
    assert client.get("/api/jobs").json()["jobs"] == []
    assert client.get("/api/library").json()["items"] == []
    assert [x["id"] for x in client.get("/api/projects").json()["projects"]] == []
    assert "ada's" not in client.get("/api/runs/run1/state", params={"path": "/secret"}).text
    assert client.get("/api/runs").json()["runs"] == []
    # and Ada finds all of it as she left it
    client.post("/api/auth/login", json=ADA)
    assert client.get("/api/projects/{}".format(p)).json()["project"]["name"] == "Ada's film"
    assert client.get("/api/library/{}".format(i)).json()["name"] == "Fox"
    assert client.get("/api/boards/canvas", params={"project": p}).json()["data"] == {"ada": 1}
    assert client.get("/api/agent/plans/{}".format(plan)).json()["state"] == "waiting"   # not stopped, approved or resumed by Bob
    assert [x["name"] for x in client.get("/api/kit", params={"project": p}).json()["entries"]] == ["Script"]
    assert client.get("/api/runs/run1/state", params={"path": "/secret"}).json()["value"] == "ada's"


# ---------------------------------------------------------------- errors are JSON, and the request's fault is a 400

# ---------------------------------------------------------------- skills: read in the studio, changed in the console

# ---------------------------------------------------------------- the console's other routes that had no test

def test_the_cast_of_a_project_is_its_always_on_entries(client):
    signed_in(client)
    project = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    client.post("/api/kit", json={"project_id": project, "text": "Fade in.", "name": "Script", "always": True})
    assert [e["name"] for e in client.get("/api/cast", params={"project": project}).json()["always"]] == ["Script"]
    assert client.get("/api/cast", params={"project": 0}).json() == {"always": [], "fills": []}

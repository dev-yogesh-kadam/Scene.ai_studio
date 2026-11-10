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

def test_a_crash_is_answered_as_json_without_a_trace(client, monkeypatch):
    from fastapi.testclient import TestClient
    signed_in(client)
    quiet = TestClient(client.app, raise_server_exceptions=False)
    quiet.cookies = client.cookies

    def boom(user_id):
        raise RuntimeError("secret table internals at line 42")
    monkeypatch.setattr(client.app.state.jobs, "snapshot", boom)
    answer = quiet.get("/api/jobs")
    assert answer.status_code == 500 and answer.headers["content-type"] == "application/json"
    assert "went wrong" in answer.json()["detail"] and "secret" not in answer.text and "Traceback" not in answer.text

    import psycopg

    def wrong_kind(user_id):
        raise psycopg.errors.InvalidTextRepresentation('invalid input syntax for type integer: "x" (column jobs.id)')
    monkeypatch.setattr(client.app.state.jobs, "snapshot", wrong_kind)
    answer = quiet.get("/api/jobs")
    assert answer.status_code == 400 and "not of the right kind" in answer.json()["detail"] and "jobs.id" not in answer.text


def test_fields_of_the_wrong_kind_are_listed_without_what_was_sent(client):
    signed_in(client)
    png = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"secret words"
    for path in ("/api/projects", "/api/agent/plans", "/api/preferences"):   # a file where JSON goes: was a crash
        answer = client.request("PUT" if path == "/api/preferences" else "POST", path, files={"file": ("a.png", png, "image/png")})
        assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["body"], path
        assert "secret words" not in answer.text and "input" not in answer.json()["detail"][0]
    assert "x" * 1000 not in client.post("/api/projects", content=json.dumps(["x" * 5000]),
                                         headers={"content-type": "application/json"}).text   # nothing sent is echoed


def test_the_api_maps_are_off_on_both_sites(client):
    for site in (client, client.console):
        for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
            answer = site.get(path)   # the console answers a one-word path with its own page (a section's address)
            assert answer.status_code == 404 or (site is client.console and "Admin console" in answer.text), path
            assert "swagger" not in answer.text.lower() and "redoc" not in answer.text.lower() and '"openapi"' not in answer.text


def test_a_body_or_a_project_id_of_the_wrong_kind_is_refused_not_a_crash(client):
    signed_in(client)
    project = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    for path in ("/api/kit", "/api/kit/sheet"):
        for body in (b"not json", b"[]", b"5", b'"words"'):
            answer = client.post(path, content=body, headers={"content-type": "application/json"})
            assert answer.status_code == 400 and isinstance(answer.json()["detail"], str), (path, body)
    for wrong in ("x", ["1"], {"id": 1}, -3, 2 ** 40, True, "12x"):
        for method, path, body in (("post", "/api/kit", {"project_id": wrong, "text": "Fade in.", "name": "S"}),
                                   ("post", "/api/kit/order", {"project_id": wrong, "ids": []}),
                                   ("put", "/api/core/state", {"project_id": wrong, "path": "/x", "value": 1}),
                                   ("put", "/api/boards/canvas", {"project": wrong, "data": {}}),
                                   ("post", "/api/agent/session/compact", {"project_id": wrong, "run": "t1"})):
            answer = getattr(client, method)(path, json=body)
            assert answer.status_code == 400 and answer.json()["detail"] == "That is not a project's id.", (path, wrong, answer.text)
    # a project's id as a form gives it (digits) still works, and ids of the wrong kind in a list are left out
    added = client.post("/api/kit", data={"project_id": str(project)}, files={"file": ("a.txt", b"Fade in.", "text/plain")})
    assert added.status_code == 200, added.text
    assert client.post("/api/kit/order", json={"project_id": project, "ids": 5}).status_code == 200
    assert client.post("/api/kit/order", json={"project_id": project, "ids": ["x", True, None]}).status_code == 200


def test_a_runs_state_is_deleted_off_the_event_loop(client):
    signed_in(client)
    client.put("/api/runs/run1/state", json={"path": "/shots/1", "value": "a"})
    client.put("/api/runs/run1/state", json={"path": "/shots/2", "value": "b"})
    assert client.delete("/api/runs/run1/state", params={"path": "/shots/1"}).json() == {"deleted": 1}
    assert "/shots/1" not in client.get("/api/runs/run1/state", params={"path": "/shots"}).text


# ---------------------------------------------------------------- skills: read in the studio, changed in the console

@pytest.fixture
def skills_here(monkeypatch, tmp_path):
    """The skills and their drafts in a folder of the test's own: the console's routes write files."""
    from scene import skills
    import inspect
    for name in ("load", "find", "save", "remove", "drafts", "publish", "discard", "save_draft"):
        real = getattr(skills, name)
        place = list(inspect.signature(real).parameters).index("folder")

        def here(*args, _real=real, _place=place, **kwargs):
            return _real(*args, **kwargs) if len(args) > _place or "folder" in kwargs else _real(*args, folder=tmp_path, **kwargs)
        monkeypatch.setattr(skills, name, here)
    (tmp_path / "reel.md").write_text("id: reel\ntitle: Reel\ndescription: Use for reels\n---\n1. Ask the length.", encoding="utf-8")
    return skills


def test_the_studio_lists_skills_and_drafts_and_never_publishes_one(client, skills_here):
    from test_api import ADMIN, console
    admin = client.post("/api/auth/register", json=ADMIN).json()
    assert [s["id"] for s in client.get("/api/skills").json()["skills"]] == ["reel"]
    draft = skills_here.save_draft({"title": "Chai ad", "desc": "Use for a tea ad", "text": "1. Ask the brand."}, {"id": admin["id"], "name": "Ada"})
    listed = client.get("/api/skills/drafts").json()
    assert [d["id"] for d in listed["drafts"]] == [draft["id"]] and listed["can_publish"] is False
    refused = client.post("/api/skills/drafts/{}/publish".format(draft["id"]), json={})
    assert refused.status_code == 403 and "admin console" in refused.json()["detail"]   # even for an admin, on this site
    assert skills_here.find(draft["id"]) is None
    assert client.delete("/api/skills/drafts/nope").status_code == 404
    signed_in(client, BOB)
    assert client.get("/api/skills/drafts").json()["drafts"] == []   # another's draft is not listed
    assert client.delete("/api/skills/drafts/{}".format(draft["id"])).status_code == 403
    client.post("/api/auth/login", json=ADMIN)
    assert client.delete("/api/skills/drafts/{}".format(draft["id"])).json() == {"ok": True}
    # the console publishes, and writes it down
    desk = console(client)
    again = skills_here.save_draft({"title": "Chai ad", "desc": "Use for a tea ad", "text": "1. Ask the brand."}, {"id": admin["id"], "name": "Ada"})
    assert desk.get("/api/admin/skills/drafts").json()["drafts"][0]["id"] == again["id"]
    published = desk.post("/api/admin/skills/drafts/{}/publish".format(again["id"]), json={"title": "Tea ad"}).json()["skill"]
    assert published["title"] == "Tea ad" and skills_here.find(again["id"])
    third = skills_here.save_draft({"title": "Gone", "text": "1."}, {"id": admin["id"]})
    assert desk.delete("/api/admin/skills/drafts/{}".format(third["id"])).json() == {"ok": True}
    assert desk.delete("/api/admin/skills/drafts/{}".format(third["id"])).status_code == 404
    actions = [e["action"] for e in desk.get("/api/admin/audit").json()["entries"]]
    assert "Published skill" in actions and "Discarded skill draft" in actions


def test_the_console_makes_changes_and_deletes_a_skill_and_writes_each_down(client, skills_here):
    from test_api import ADMIN, console
    client.post("/api/auth/register", json=ADMIN)
    desk = console(client)
    assert [s["id"] for s in desk.get("/api/admin/skills").json()["skills"]] == ["reel"]
    made = desk.post("/api/admin/skills", json={"id": "promo", "title": "Promo", "desc": "Use for promos", "text": "1. Ask."})
    assert made.status_code == 200 and made.json()["skill"]["id"] == "promo"
    assert desk.post("/api/admin/skills", json={"id": "promo", "title": "Again", "text": "1."}).status_code == 400
    assert desk.put("/api/admin/skills/promo", json={"title": "Promo 2", "text": "1. Ask twice."}).json()["skill"]["title"] == "Promo 2"
    assert desk.put("/api/admin/skills/nope", json={"title": "x"}).status_code == 404
    assert desk.delete("/api/admin/skills/promo").json() == {"ok": True}
    assert desk.delete("/api/admin/skills/promo").status_code == 404
    assert desk.delete("/api/admin/skills/..%2Freel").status_code == 404 and skills_here.find("reel")
    actions = [e["action"] for e in desk.get("/api/admin/audit").json()["entries"]]
    assert {"Created skill", "Edited skill", "Deleted skill"} <= set(actions)


# ---------------------------------------------------------------- the console's other routes that had no test

def test_the_consoles_home_page_files_and_backup_check_answer_cleanly(client):
    from test_api import ADMIN, console
    client.post("/api/auth/register", json=ADMIN)
    desk = console(client)
    for site, path in ((desk, "/api/admin/showcase/nope/file"), (desk, "/api/admin/showcase/nope/poster"),
                       (client, "/api/showcase/nope/file"), (client, "/api/showcase/nope/poster")):
        answer = site.get(path)
        assert answer.status_code == 404 and answer.json()["detail"] == "No such item on the Home page.", path
    for body in ({"items": 5}, {"items": [1, 2]}, {"sections": "Films"}):
        assert desk.put("/api/admin/showcase", json=body).status_code == 400, body
    assert desk.put("/api/admin/showcase", json={"sections": ["Films"], "items": []}).json()["sections"] == ["Films"]
    checked = desk.post("/api/admin/backups/check")
    assert checked.status_code == 200 and isinstance(checked.json()["ok"], bool)
    assert "Checked the newest backup" in [e["action"] for e in desk.get("/api/admin/audit").json()["entries"]]


def test_the_consoles_people_come_a_page_at_a_time(client, monkeypatch):
    from test_api import ADMIN, console
    client.app.state.settings.signups_per_day = 0   # five sign-ups from one address
    client.post("/api/auth/register", json=ADMIN)
    for n in range(4):
        made = client.post("/api/auth/register", json={"email": "p{}@example.com".format(n), "password": "correct horse"})
        assert made.status_code == 200, made.text
    desk = console(client)
    everyone = desk.get("/api/admin/users").json()
    assert len(everyone["users"]) == 5 and everyone["next_offset"] is None
    first = desk.get("/api/admin/users", params={"limit": 2}).json()
    second = desk.get("/api/admin/users", params={"limit": 2, "offset": first["next_offset"]}).json()
    last = desk.get("/api/admin/users", params={"limit": 2, "offset": second["next_offset"]}).json()
    assert [u["id"] for u in first["users"] + second["users"] + last["users"]] == [u["id"] for u in everyone["users"]]
    assert last["next_offset"] is None
    assert len(desk.get("/api/admin/users", params={"limit": 10_000}).json()["users"]) == 5   # held to the most a page holds


def test_the_cast_of_a_project_is_its_always_on_entries(client):
    signed_in(client)
    project = client.post("/api/projects", json={"name": "Film"}).json()["id"]
    client.post("/api/kit", json={"project_id": project, "text": "Fade in.", "name": "Script", "always": True})
    assert [e["name"] for e in client.get("/api/cast", params={"project": project}).json()["always"]] == ["Script"]
    assert client.get("/api/cast", params={"project": 0}).json() == {"always": [], "fills": []}


def test_search_by_meaning_falls_back_to_words_when_the_embedding_api_is_down(client, monkeypatch):
    from scene import semantic
    from test_api import register
    register(client)
    monkeypatch.setattr(client.app.state, "embedder", object())   # search by meaning is on

    def down(*args, **kwargs):
        raise semantic.SemanticError("The embedding API can't be reached.")
    monkeypatch.setattr(semantic, "nearest", down)
    answer = client.get("/api/library?q=kite&meaning=1")
    assert answer.status_code == 200 and answer.json()["items"] == []   # the word search's answer, not a 500

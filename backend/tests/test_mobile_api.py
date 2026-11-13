"""The phone site's own routes: the lighter job and library lists, modules, running a job again, credits, share links."""

import json
import time
import uuid


ADA = {"email": "ada@example.com", "password": "correct horse"}


def signed_in(client, who=ADA):
    client.cookies.clear()
    return client.post("/api/auth/register", json=who).json()


def item(client, user_id, name, kind="video", rating=0, job_id=None, created=None, run=""):
    return client.app.state.db.run(
        "INSERT INTO generations (user_id, job_id, workflow, kind, name, filename, summary, settings, context, seconds, size, "
        "created, rating, run) VALUES (?, ?, 'video/x', ?, ?, 'missing.mp4', '', ?, ?, 5, 100, ?, ?, ?)",
        (user_id, job_id, kind, name, json.dumps({"prompt": "a fox in snow " + name, "workflow_title": "LTX"}),
         json.dumps({"width": 1280, "height": 720, "orientation": "landscape"}), created or time.time(), rating, run))


def job(client, user_id, name="Fox", status="failed", cost=10):
    """A job that already ended (put straight in the table, so the queue never picks it up)."""
    job_id = uuid.uuid4().hex[:12]
    client.app.state.db.run(
        "INSERT INTO jobs (id, user_id, name, workflow, kind, settings, summary, status, error, est_seconds, cost, created, finished) "
        "VALUES (?, ?, ?, 'video/video_ltx2_5_t2v', 'video', ?, '', ?, 'boom', 60, ?, ?, ?)",
        (job_id, user_id, name, json.dumps({"prompt": "a fox"}), status, cost, time.time(), time.time()))
    return job_id














# ---------------------------------------------------------------- jobs, library, credits

def test_mobile_jobs_are_light_and_carry_what_they_made(client):
    ada = signed_in(client)
    done_id = job(client, ada["id"], "Fox", status="done")
    made = item(client, ada["id"], "Fox", job_id=done_id)
    failed_id = job(client, ada["id"], "Owl", status="failed")
    answer = client.get("/api/mobile/jobs").json()
    assert answer["paused"] is False
    jobs = {j["id"]: j for j in answer["jobs"]}
    assert "settings" not in jobs[done_id] and jobs[done_id]["prompt"] == "a fox"
    assert jobs[done_id]["items"] == [{"id": made, "kind": "video"}]
    assert jobs[failed_id]["status"] == "failed" and jobs[failed_id]["reason"]


def test_mobile_library_pages_filters_and_stars(client):
    ada = signed_in(client)
    for i in range(5):
        item(client, ada["id"], "clip {}".format(i), created=1000 + i, rating=1 if i == 2 else 0)
    item(client, ada["id"], "still", kind="image", created=2000)
    item(client, ada["id"], "working file", created=3000, run="r1")   # a run's working files are left out
    first = client.get("/api/mobile/library?limit=4").json()
    assert [i["name"] for i in first["items"]] == ["still", "clip 4", "clip 3", "clip 2"] and first["next_offset"] == 4
    rest = client.get("/api/mobile/library?limit=4&offset=4").json()
    assert [i["name"] for i in rest["items"]] == ["clip 1", "clip 0"] and rest["next_offset"] is None
    shown = first["items"][1]
    assert shown["width"] == 1280 and shown["prompt"].startswith("a fox") and shown["mine"] is True and "settings" not in shown
    assert [i["name"] for i in client.get("/api/mobile/library?kind=image").json()["items"]] == ["still"]
    assert [i["name"] for i in client.get("/api/mobile/library?starred=1").json()["items"]] == ["clip 2"]
    assert [i["name"] for i in client.get("/api/mobile/library?q=clip 3").json()["items"]] == ["clip 3"]


def test_another_users_items_are_not_listed(client):
    ada = signed_in(client)
    item(client, ada["id"], "mine")
    signed_in(client, {"email": "bob@example.com", "password": "correct horse"})
    assert client.get("/api/mobile/library").json()["items"] == []


def test_credits_show_the_balance_and_the_latest_changes(client):
    signed_in(client)
    answer = client.get("/api/mobile/credits").json()
    assert answer["balance"] == 500 and answer["events"][0]["amount"] == 500


def test_mobile_workflows_are_the_ones_a_prompt_alone_can_start(client):
    signed_in(client)
    found = {w["id"]: w for w in client.get("/api/mobile/workflows").json()["workflows"]}
    assert found, "some workflow needs only a prompt"
    for workflow in found.values():
        assert workflow["kind"] in ("video", "image", "audio")
        assert any(c["role"] == "prompt" for c in workflow["controls"]) or workflow["refs"]
        assert all(c["role"] != "seed" for c in workflow["controls"])


# ---------------------------------------------------------------- running a job again

def test_a_failed_job_runs_again_for_its_price(client):
    ada = signed_in(client)
    client.app.state.jobs.pause(True)   # the new job stays queued while it is looked at
    failed_id = job(client, ada["id"], "Fox", status="failed", cost=10)
    before =client.get("/api/mobile/credits").json()["balance"]
    again = client.post("/api/jobs/{}/retry".format(failed_id)).json()
    assert again["credits"] == 10 and again["id"] != failed_id
    assert client.get("/api/mobile/credits").json()["balance"] == before - 10
    queued = client.app.state.db.one("SELECT name, status FROM jobs WHERE id = ?", (again["id"],))
    assert queued == {"name": "Fox", "status": "queued"}


def test_only_ones_own_failed_jobs_run_again(client):
    ada = signed_in(client)
    done_id = job(client, ada["id"], status="done")
    assert client.post("/api/jobs/{}/retry".format(done_id)).status_code == 400
    failed_id = job(client, ada["id"], status="failed")
    signed_in(client, {"email": "bob@example.com", "password": "correct horse"})
    assert client.post("/api/jobs/{}/retry".format(failed_id)).status_code == 404
    assert client.post("/api/jobs/nope/retry").status_code == 404


def test_a_retry_with_too_few_credits_is_refused(client):
    ada = signed_in(client)
    failed_id = job(client, ada["id"], status="failed", cost=10_000)
    answer = client.post("/api/jobs/{}/retry".format(failed_id))
    assert answer.status_code in (402, 429)


def test_one_item_opens_for_the_player(client):
    ada = signed_in(client)
    made = item(client, ada["id"], "Fox")
    shown = client.get("/api/mobile/library/{}".format(made)).json()
    assert shown["id"] == made and shown["name"] == "Fox" and shown["ext"] == ".mp4" and shown["mine"] is True
    signed_in(client, {"email": "bob@example.com", "password": "correct horse"})
    assert client.get("/api/mobile/library/{}".format(made)).status_code == 404


def test_every_phone_workflow_prices_and_starts_with_the_settings_the_app_sends(client):
    """The Create screen sends each control's default, the prompt typed, and each option's default."""
    signed_in(client)
    client.app.state.jobs.pause(True)
    client.app.state.db.run("UPDATE users SET credits = 100000")

    class Unlimited:   # one job a workflow, 40-odd of them: more than the jobs route lets one person send a minute
        remote = False

        def allow(self, *args):
            return True
    client.app.state.limits = Unlimited()
    for workflow in client.get("/api/mobile/workflows").json()["workflows"]:
        if any(not r["optional"] for r in workflow["refs"]):
            continue   # it needs a picture or a video uploaded with it
        values = {c["id"]: ("a fox in the snow" if c["role"] == "prompt" else c["default"]) for c in workflow["controls"]}
        settings = {"workflow": workflow["id"], "values": values, "options": {o["id"]: o["default"] for o in workflow["options"]}}
        priced = client.post("/api/estimate", json=settings)
        assert priced.status_code == 200, (workflow["id"], priced.json())
        started = client.post("/api/jobs", data={"settings": json.dumps(dict(settings, name="a fox in the snow"))})
        assert started.status_code == 200, (workflow["id"], started.json())


def shot_item(client, user_id, project_id, name, shot=None, created=None):
    settings = {"prompt": name}
    if shot:
        settings["shot_number"] = shot
    return client.app.state.db.run(
        "INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, created, project_id) "
        "VALUES (?, 'video/x', 'video', ?, 'missing.mp4', '', ?, '{}', ?, ?)",
        (user_id, name, json.dumps(settings), created or time.time(), project_id))


def test_a_module_reads_as_story_shots_and_boards(client):
    from scene import placement
    ada = signed_in(client)
    project = client.post("/api/projects", json={"name": "Fox Film"}).json()
    module = client.post("/api/projects", json={"name": "Scene 1", "parent_id": project["id"]}).json()
    take1 = shot_item(client, ada["id"], module["id"], "shot 2 take 1", shot=2, created=1000)
    take2 = shot_item(client, ada["id"], module["id"], "shot 2 take 2", shot=2, created=2000)
    first = shot_item(client, ada["id"], module["id"], "shot 1", shot=1, created=1500)
    loose = shot_item(client, ada["id"], module["id"], "a still", created=3000)
    fox = shot_item(client, ada["id"], module["id"], "Violet", created=500)
    placement.place(client.app.state.db, {"user_id": ada["id"], "project_id": module["id"], "workflow": "image/x",
                                          "settings": {"board": "Characters", "placement_group": "violet"}}, fox)
    shot_item(client, ada["id"], project["id"], "on the main canvas")

    answer = client.get("/api/mobile/modules/{}".format(module["id"])).json()
    assert answer["module"]["name"] == "Scene 1" and answer["module"]["project"]["name"] == "Fox Film" and answer["module"]["main"] is False
    assert [s["number"] for s in answer["shots"]] == [1, 2]
    assert [t["id"] for t in answer["shots"][1]["takes"]] == [take2, take1] and answer["shots"][0]["takes"][0]["id"] == first
    assert [(b["name"], [i["id"] for i in b["stacks"][0]["items"]]) for b in answer["boards"]] == [("Characters", [fox])]
    assert answer["items"] == 5 and loose

    main = client.get("/api/mobile/modules/{}".format(project["id"])).json()
    assert main["module"]["main"] is True and main["items"] == 1
    # The library list: a project with its modules, or with exact=1 just its own canvas.
    assert len(client.get("/api/mobile/library?project={}".format(project["id"])).json()["items"]) == 6
    assert [i["name"] for i in client.get("/api/mobile/library?project={}&exact=1".format(project["id"])).json()["items"]] == ["on the main canvas"]

    signed_in(client, {"email": "bob@example.com", "password": "correct horse"})
    assert client.get("/api/mobile/modules/{}".format(module["id"])).status_code == 404


# ---------------------------------------------------------------- share links, credit requests, waiting plans, live events

def test_a_share_link_opens_the_item_without_signing_in_until_it_is_stopped(client, tmp_path):
    ada = signed_in(client)
    made = item(client, ada["id"], "Fox")
    folder = client.app.state.outputs.folder(ada["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "missing.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    link = client.post("/api/library/{}/share".format(made)).json()
    assert link["path"].startswith("/s/") and link["expires"] > time.time()

    client.cookies.clear()   # someone else, not signed in
    page = client.get(link["path"])
    assert page.status_code == 200 and "<video" in page.text and "Fox" in page.text
    assert client.get(link["path"] + "/file").status_code == 200
    assert client.get("/s/not-a-real-token").status_code == 404

    client.post("/api/auth/login", json=ADA)
    assert client.delete("/api/library/{}/share".format(made)).json() == {"ok": True}
    client.cookies.clear()
    assert client.get(link["path"]).status_code == 404


def test_only_the_owner_shares_and_links_can_be_turned_off(client):
    ada = signed_in(client)
    made = item(client, ada["id"], "Fox")
    signed_in(client, {"email": "bob@example.com", "password": "correct horse"})
    assert client.post("/api/library/{}/share".format(made)).status_code == 404
    client.app.state.settings.share_days = 0
    client.post("/api/auth/login", json=ADA)
    assert client.post("/api/library/{}/share".format(made)).status_code == 403




def test_plans_waiting_for_approval_are_listed(client):
    signed_in(client)
    project = client.post("/api/projects", json={"name": "Fox Film"}).json()
    client.put("/api/boards/agent", json={"project": project["id"], "data": {"tabs": [{"id": "t1", "name": "Agent 1"}]}})
    runs_ = [{"instruction": "make a fox", "reply": "Here is a plan", "state": "answered", "steps": []},
             {"instruction": "now three shots", "reply": "Three shots", "state": "proposed", "steps": [{}, {}, {}], "total": 300, "at": 1}]
    client.put("/api/boards/agent-t1", json={"project": project["id"], "data": {"runs": runs_}})
    plans = client.get("/api/mobile/waiting").json()["plans"]
    assert len(plans) == 1 and plans[0]["tab_name"] == "Agent 1" and plans[0]["steps"] == 3 and plans[0]["total"] == 300
    assert plans[0]["project"] == "Fox Film" and plans[0]["instruction"] == "now three shots"
    runs_[1]["state"] = "approved"
    client.put("/api/boards/agent-t1", json={"project": project["id"], "data": {"runs": runs_}})
    assert client.get("/api/mobile/waiting").json()["plans"] == []




def test_workflows_that_need_a_picture_are_offered_with_their_slots(client):
    signed_in(client)
    found = client.get("/api/mobile/workflows").json()["workflows"]
    with_refs = [w for w in found if any(not r["optional"] for r in w["refs"])]
    assert with_refs, "a workflow that needs a picture or a video"
    for workflow in found:
        for ref in workflow["refs"]:
            assert set(ref) == {"id", "kind", "label", "optional"}


def test_a_credit_request_is_logged_for_the_admins(client):
    signed_in(client)
    assert client.post("/api/mobile/credit-request", json={"amount": 0}).status_code == 400
    assert client.post("/api/mobile/credit-request", json={"amount": 500, "note": "for the trailer"}).json() == {"ok": True}
    logged = client.app.state.db.one("SELECT action, detail FROM audit_log WHERE action = 'Asked for credits'")
    assert logged["detail"] == "500 cr · for the trailer"


# ---------------------------------------------------------------- the phone site (/m/)

PHONE = {"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"}
TABLET = {"User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
LAPTOP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def built_site(client, tmp_path):
    site = tmp_path / "phone-site"
    (site / "_expo" / "static" / "js").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>Scene.ai</title><div id=root></div>", encoding="utf-8")
    (site / "_expo" / "static" / "js" / "entry-abc.js").write_text("console.log(1)", encoding="utf-8")
    client.app.state.settings.mobile_site_dir = str(site)
    return site


def test_a_phone_is_sent_to_the_same_place_on_the_phone_site(client, tmp_path):
    ada = signed_in(client)
    project = client.post("/api/projects", json={"name": "Fox Film"}).json()
    module = client.post("/api/projects", json={"name": "Scene 1", "parent_id": project["id"]}).json()
    refs = {r["id"]: r["ref"] for r in client.get("/api/projects").json()["projects"]}
    site_client = client
    # The site's folder is read when the app is made: point it at a built site and make the app again.
    from fastapi.testclient import TestClient
    from scene.main import create_app
    settings = client.app.state.settings
    built_site(client, tmp_path)
    with TestClient(create_app(settings)) as site_client:
        site_client.post("/api/auth/login", json=ADA)
        go = lambda path, who=PHONE: site_client.get(path, headers=who, follow_redirects=False)
        assert go("/").headers["location"] == "/m/"
        assert go("/library").headers["location"] == "/m/library"
        assert go("/canvas/{}/module/{}".format(refs[project["id"]], refs[module["id"]])).headers["location"] == "/m/canvas/{}".format(module["id"])
        assert go("/project/{}".format(refs[project["id"]])).headers["location"] == "/m/project/{}".format(project["id"])
        assert go("/", TABLET).status_code == 200 and go("/", LAPTOP).status_code == 200   # the full studio
        assert go("/api/auth/me").status_code == 200   # the API is never redirected
        assert ada


def test_the_phone_site_answers_every_screen_and_keeps_its_scripts(client, tmp_path):
    from fastapi.testclient import TestClient
    from scene.main import create_app
    built_site(client, tmp_path)
    with TestClient(create_app(client.app.state.settings)) as site_client:
        for path in ("/m", "/m/", "/m/canvas/12", "/m/library"):
            page = site_client.get(path, headers=PHONE)
            assert page.status_code == 200 and "<div id=root>" in page.text, path
        # A module's old address goes to its canvas
        assert site_client.get("/m/module/12", follow_redirects=False).headers["location"] == "/m/canvas/12"
        script = site_client.get("/m/_expo/static/js/entry-abc.js")
        assert script.status_code == 200 and "immutable" in script.headers["cache-control"]
        # A script or font of an earlier build is not found, not answered with the page
        assert site_client.get("/m/_expo/static/js/web/[id]-old.js").status_code == 404
        assert site_client.get("/m/assets/Ionicons.old.ttf").status_code == 404
        assert site_client.get("/m/../../config.json").status_code in (200, 404) and "secret" not in site_client.get("/m/../../config.json").text


def test_the_full_studio_on_a_phone_is_remembered_until_the_phone_site_is_opened(client, tmp_path):
    from fastapi.testclient import TestClient
    from scene.main import create_app
    built_site(client, tmp_path)
    with TestClient(create_app(client.app.state.settings)) as site_client:
        chosen = site_client.get("/?desktop=1", headers=PHONE, follow_redirects=False)
        assert chosen.status_code == 200 and "scene_desktop" in chosen.headers.get("set-cookie", "")
        assert site_client.get("/library", headers=PHONE, follow_redirects=False).status_code == 200   # stays on the studio
        site_client.get("/m/", headers=PHONE)
        assert site_client.get("/library", headers=PHONE, follow_redirects=False).status_code == 302


def test_without_a_built_site_phones_get_the_studio_and_m_says_how_to_build_it(client, tmp_path):
    client.app.state.settings.mobile_site_dir = str(tmp_path / "nothing-here")
    from fastapi.testclient import TestClient
    from scene.main import create_app
    with TestClient(create_app(client.app.state.settings)) as site_client:
        assert site_client.get("/", headers=PHONE, follow_redirects=False).status_code == 200
        page = site_client.get("/m/", headers=PHONE)
        assert page.status_code == 503 and "npm run build" in page.text


def test_the_live_events_open_with_the_session_cookie(client):
    signed_in(client)
    with client.websocket_connect("/api/events") as ws:
        first = json.loads(ws.receive_text())
        assert "jobs" in first and first["credits"] == 500


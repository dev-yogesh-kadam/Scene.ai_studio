"""The Scene Provider API v1 adapter (providers/v1.py) against a fake v1 server (fake_v1.py), and a job made through it
with the provider router on (jobs._run_provider); shadow mode, and ComfyUI's renders left as they were."""

import asyncio
import json
import time

import pytest

from fake_v1 import FakeV1
from scene.providers import registry, router as router_module, v1
from scene.providers.base import KeyProblem, ProviderProblem, RequestProblem
from scene.providers.router import Router
from test_api import console, register


def adapter(fake):
    return v1.V1("http://fake-v1", http=fake.client())


@pytest.fixture(autouse=True)
def quick_polls(monkeypatch):
    monkeypatch.setattr(v1, "POLL_FIRST", 0.01)
    monkeypatch.setattr(v1, "POLL_MOST", 0.02)


# ---------------------------------------------------------------- the adapter

def test_whoami_models_and_errors_by_the_contracts_table():
    fake = FakeV1()

    async def go():
        a = adapter(fake)
        said = await a.whoami("sa_live_alpha1234")
        assert said["credits"]["available"] == 91296 and said["key"]["max_concurrent"] == 2
        assert [m["id"] for m in await a.models("sa_live_alpha1234")] == ["seedance_2_5", "speech"]   # the provider's ids
        with pytest.raises(KeyProblem) as bad:
            await a.whoami("sa_live_nobody00")
        assert (bad.value.status, bad.value.code, bad.value.request_id) == ("invalid", "key_invalid", "req_err")
        fake.no_credit.add("sa_live_alpha1234")
        with pytest.raises(KeyProblem) as broke:
            await a.models("sa_live_alpha1234")
        assert broke.value.status == "no_credit"
        fake.no_credit.clear()
        fake.limited.add("sa_live_alpha1234")
        with pytest.raises(KeyProblem) as busy:
            await a.models("sa_live_alpha1234")
        assert (busy.value.status, busy.value.retry_after) == ("rate_limited", 30)
        fake.limited.clear()
        fake.unavailable.add("seedance_2_5")
        with pytest.raises(ProviderProblem):
            await a.start("sa_live_alpha1234", "seedance_2_5", {"prompt": "x"}, {}, "scene-job-1")
        fake.unavailable.clear()
        fake.refuse = True
        with pytest.raises(RequestProblem, match="duration must be at most 15"):
            await a.start("sa_live_alpha1234", "seedance_2_5", {"prompt": "x"}, {}, "scene-job-2")
    asyncio.run(go())


def test_a_retry_reuses_the_idempotency_key_and_never_pays_twice():
    fake = FakeV1()

    async def go():
        a = adapter(fake)
        first = await a.start("sa_live_alpha1234", "seedance_2_5", {"prompt": "x"}, {"scene": {"job": {"id": 9}}}, v1.idempotency_key(9))
        again = await a.start("sa_live_alpha1234", "seedance_2_5", {"prompt": "x"}, {"scene": {"job": {"id": 9}}}, v1.idempotency_key(9))
        assert first["id"] == again["id"] and again["replayed"] and not first["replayed"]
        assert first["quote"] == {"credits": 13, "source": "price_list"}   # the price list's estimate at POST
        posts = [c for c in fake.calls if c["path"] == "/v1/jobs"]
        assert [c["idempotency"] for c in posts] == ["scene-job-9", "scene-job-9"] and len(fake.jobs) == 1
        assert v1.idempotency_key(9, clip=2) == "scene-job-9-clip-2"
        answer = await a.follow("sa_live_alpha1234", first["id"])
        assert answer["status"] == "succeeded" and answer["quote"]["source"] == "provider" and answer["cost"] == 65
    asyncio.run(go())


def test_polling_returns_the_cost_only_once_finished_and_a_test_key_stops_at_the_quote():
    fake = FakeV1(polls=3)
    seen = []

    async def go():
        a = adapter(fake)
        started = await a.start("sa_test_beta5678", "seedance_2_5", {"prompt": "x"}, {}, "scene-job-3")
        answer = await a.follow("sa_test_beta5678", started["id"], on_change=lambda s: seen.append((s["status"], s["cost"])))
        problem = v1.job_problem(answer)
        assert isinstance(problem, v1.TestMode) and problem.credits == 65 and str(problem) == (
            "Test mode: would cost 65 credits (A test key stops at the quote.).")
    asyncio.run(go())
    assert seen == [("running", None), ("running", None), ("failed", 0)]   # cost is null until it ends


def test_a_cancel_says_whether_the_provider_charges():
    fake = FakeV1(polls=50)

    async def go():
        a = adapter(fake)
        started = await a.start("sa_live_alpha1234", "seedance_2_5", {"prompt": "x"}, {}, "scene-job-4")
        answer = await a.follow("sa_live_alpha1234", started["id"], cancelled=lambda: True)
        assert answer["studio_cancelled"] and answer["charged"] is False   # it had not reached the provider
    asyncio.run(go())


# ---------------------------------------------------------------- a job through the provider

def a_provider(client, monkeypatch, fake, secret="sa_live_alpha1234"):
    monkeypatch.setattr(router_module, "V1", lambda base_url: v1.V1(base_url, http=fake.client()))
    register(client)
    desk = console(client)
    added = desk.post("/api/admin/providers/keys", json={"kind": "scene_provider_v1", "base_url": "http://fake-v1",
                                                         "name": "Generation server", "secret": secret, "label": "studio A"}).json()
    assert added["saved"], added
    return desk, added


def wait_for(client, job_id, seconds=30):
    for _ in range(int(seconds * 10)):
        job = next((j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job_id), None)
        if job and job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.1)
    raise AssertionError("the job did not end")


SEEDANCE_JOB = {"workflow": "video/@seedance_2_5", "values": {}, "options": {"resolution": "720p"}, "name": "shot 3"}


def prompt_of(client):
    schema = client.get("/api/workflows/video/@seedance_2_5").json()
    roles = {c["role"]: c["id"] for c in schema["controls"] if c["role"]}
    return schema, roles


def test_with_the_router_on_a_providers_model_is_offered_made_and_filed(client, monkeypatch):
    fake = FakeV1()
    desk, _ = a_provider(client, monkeypatch, fake)
    ids = [w["id"] for w in client.get("/api/workflows").json()["workflows"]]
    assert "video/@seedance_2_5" not in ids and "video/generation_video" in ids   # off: the ComfyUI disguise as before
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    listed = {w["id"]: w for w in client.get("/api/workflows").json()["workflows"]}
    assert "video/@seedance_2_5" in listed and "audio/@speech" in listed and "video/generation_video" not in listed
    assert listed["video/@seedance_2_5"]["source"] == "generation" and listed["video/@seedance_2_5"]["title"] == "Seedance 2.5"
    schema, roles = prompt_of(client)
    assert [o["id"] for o in schema["options"]] == ["resolution", "aspect_ratio", "sound"] and schema["chain"]   # a first frame: chained
    too_long = dict(SEEDANCE_JOB, values={roles["prompt"]: "a cat", roles["duration"]: 20})
    refused = client.post("/api/jobs", data={"settings": json.dumps(too_long)})
    assert refused.status_code == 400 and "4 to 15 seconds" in refused.json()["detail"]   # its limits, said before any charge
    job = dict(SEEDANCE_JOB, values={roles["prompt"]: "a cat on a roof", roles["duration"]: 5})
    job_id = client.post("/api/jobs", data={"settings": json.dumps(job)}).json()["id"]
    ended = wait_for(client, job_id)
    assert ended["status"] == "done", ended
    sent = next(c for c in fake.calls if c["path"] == "/v1/jobs")
    assert sent["body"]["model"] == "seedance_2_5" and sent["idempotency"] == "scene-job-{}".format(job_id)
    assert sent["body"]["input"] == {"prompt": "a cat on a roof", "duration": 5, "resolution": "720p", "aspect_ratio": "16:9", "sound": False}
    assert sent["body"]["metadata"]["scene"]["job"] == {"id": job_id, "name": "shot 3"}
    db = client.app.state.db
    row = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    note = json.loads(row["provider"])
    assert (row["server"], note["provider"], note["model"], note["key"], note["cost"]) == ("Generation server", "Generation server",
                                                                                          "seedance_2_5", "studio A", 65)
    assert note["request_id"] == "req_poll" and "sa_live_alpha1234" not in row["provider"]   # the label, never the key
    item = db.one("SELECT * FROM generations WHERE job_id = ?", (job_id,))
    assert item["kind"] == "video" and item["filename"].endswith(".mp4") and item["workflow"] == "video/@seedance_2_5"
    assert client.app.state.router.running == {}   # its key was let go


def test_a_test_key_stops_at_the_providers_quote_and_the_credits_come_back(client, monkeypatch):
    fake = FakeV1()
    desk, _ = a_provider(client, monkeypatch, fake, secret="sa_test_beta5678")
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    _, roles = prompt_of(client)
    before = client.get("/api/auth/me").json()["credits"]
    job_id = client.post("/api/jobs", data={"settings": json.dumps(dict(SEEDANCE_JOB, values={roles["prompt"]: "a cat"}))}).json()["id"]
    ended = wait_for(client, job_id)
    assert ended["status"] == "failed" and ended["error"].startswith("The provider: Test mode: would cost 65 credits")
    assert client.get("/api/auth/me").json()["credits"] == before


def test_a_revoked_key_fails_over_to_the_next_key_and_is_shown_invalid(client, monkeypatch):
    fake = FakeV1(live=("sa_live_alpha1234", "sa_live_gamma9999"))
    desk, added = a_provider(client, monkeypatch, fake)
    provider_id = added["provider_id"]
    desk.post("/api/admin/providers/keys", json={"provider_id": provider_id, "secret": "sa_live_gamma9999", "label": "studio B"})
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    fake.revoked.add("sa_live_alpha1234")   # revoked in Studio_automation's panel
    _, roles = prompt_of(client)
    job_id = client.post("/api/jobs", data={"settings": json.dumps(dict(SEEDANCE_JOB, values={roles["prompt"]: "a cat"}))}).json()["id"]
    assert wait_for(client, job_id)["status"] == "done"
    assert [c["last4"] for c in fake.calls if c["path"] in ("/v1/jobs",)] == ["1234", "9999"]
    keys = {k["label"]: k for k in next(p for p in desk.get("/api/admin/providers").json()["providers"] if p["id"] == provider_id)["keys"]}
    assert keys["studio A"]["status"] == "invalid" and "revoked" in keys["studio A"]["last_error"]
    assert json.loads(client.app.state.db.one("SELECT provider FROM jobs WHERE id = ?", (job_id,))["provider"])["key"] == "studio B"


def test_with_no_key_for_a_model_the_job_fails_at_once_and_its_credits_come_back(client, monkeypatch):
    fake = FakeV1()
    desk, added = a_provider(client, monkeypatch, fake)
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    _, roles = prompt_of(client)
    before = client.get("/api/auth/me").json()["credits"]
    # Its one key found broken after the model was offered (the page still shows it): the queue fails it at once.
    client.app.state.db.run("UPDATE provider_keys SET status = 'invalid' WHERE id = ?", (added["key_id"],))
    client.app.state.router.forget()
    client.app.state.catalog.providers.read_at = time.time()   # what was offered a moment ago
    job_id = client.post("/api/jobs", data={"settings": json.dumps(dict(SEEDANCE_JOB, values={roles["prompt"]: "a cat"}))}).json()["id"]
    ended = wait_for(client, job_id)
    assert ended["status"] == "failed" and ended["error"] == ("No provider has a key for Seedance 2.5: add one in Servers & APIs "
                                                              "→ Providers.")
    assert client.get("/api/auth/me").json()["credits"] == before


# ---------------------------------------------------------------- shadow mode, and ComfyUI as it was

def test_shadow_mode_changes_nothing_about_where_a_render_runs(client, monkeypatch):
    fake = FakeV1()
    desk, _ = a_provider(client, monkeypatch, fake)
    jobs, pool = client.app.state.jobs, client.app.state.comfy_pool
    pool.nodes = {s["url"]: (None, time.time()) for s in pool.servers()}
    job = {"id": "j-shadow", "workflow": "image/image_t2i_flux3_klein", "settings": json.dumps({"options": {}}), "user_id": 1}

    def place():
        return asyncio.run(jobs._place(dict(job), {}))
    off = place()
    desk.put("/api/admin/providers/router", json={"mode": "shadow"})
    assert place() == off and off[0]["url"] == "http://127.0.0.1:9"   # the balancer's pick, whatever the router says
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    assert place() == off   # ComfyUI's workflows stay with the balancer, on too
    desk.put("/api/admin/providers/router", json={"mode": "shadow"})
    db = client.app.state.db
    db.run("INSERT INTO jobs (id, user_id, name, workflow, kind, settings, status, created) VALUES (?, ?, 'x', ?, 'video', '{}', 'running', ?)",
           ("j-gen", client.get("/api/auth/me").json()["id"], "video/generation_video", time.time()))
    disguised = {"id": "j-gen", "workflow": "video/generation_video", "settings": {"options": {"model": "seedance_2_5"}}}
    asyncio.run(jobs._shadow(disguised, {"name": "Generation server", "url": "http://fake-v1"}))
    note = json.loads(db.one("SELECT provider FROM jobs WHERE id = 'j-gen'")["provider"])["shadow"]
    assert note["would"]["provider"] == "Generation server" and note["model"] == "seedance_2_5" and note["agree"] is True
    assert db.one("SELECT server FROM jobs WHERE id = 'j-gen'")["server"] in ("", None)   # the job's own row untouched


def test_the_comfyui_adapter_lists_the_studios_workflows_as_its_models(client):
    from scene.providers.comfyui import ComfyUI, capability_of
    assert [capability_of(w) for w in ("video/h3_all_in_one", "audio/audio_transcribe_video", "audio/audio_separate_voice",
                                       "upscaler/utility_seedvr2_3b_int8_upscale_video", "image/image_t2i_flux2_dev",
                                       "video/video_lipsync", "audio/audio_minimax_music_3")] == [
        "text_to_video", "transcribe", "separate_voice", "upscale_video", "image", "lip_sync", "music"]
    found = asyncio.run(ComfyUI("http://127.0.0.1:9", client.app.state.catalog).models(""))
    ids = {m["id"] for m in found}
    assert "video/h3_all_in_one" in ids and not any("generation_" in i for i in ids)
    assert next(m for m in found if m["id"] == "audio/audio_transcribe")["capability"] == "transcribe"


def tiny_mp4(seconds=1):
    """A real MP4 (a test pattern): a chain cuts the last frame from each clip and joins them."""
    import subprocess
    import tempfile
    from pathlib import Path
    from scene.media import ffmpeg_path
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp4"
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc=size=320x180:rate=24:duration={}".format(seconds), "-pix_fmt", "yuv420p", str(out)], check=True)
        return out.read_bytes()


def test_a_long_video_is_chained_clip_by_clip_on_the_providers_model(client, monkeypatch):
    fake = FakeV1()
    fake.output = tiny_mp4()
    desk, _ = a_provider(client, monkeypatch, fake)
    desk.put("/api/admin/providers/router", json={"mode": "on"})
    schema, roles = prompt_of(client)
    job = dict(SEEDANCE_JOB, clips=2, values={roles["prompt"]: "she walks to the stall\n---\nshe sits by the fountain", roles["duration"]: 5})
    made = client.post("/api/jobs", data={"settings": json.dumps(job)})
    assert made.status_code == 200, made.text
    ended = wait_for(client, made.json()["id"], seconds=60)
    assert ended["status"] == "done", ended
    sent = [c for c in fake.calls if c["path"] == "/v1/jobs"]
    assert [c["body"]["input"]["prompt"] for c in sent] == ["she walks to the stall", "she sits by the fountain"]
    assert [c["idempotency"] for c in sent] == ["scene-job-{}-clip-{}".format(ended["id"], n) for n in (1, 2)]
    assert "first_frame" not in sent[0]["body"]["input"] and sent[1]["body"]["input"]["first_frame"].startswith("file_")
    db = client.app.state.db
    note = json.loads(db.one("SELECT provider FROM jobs WHERE id = ?", (ended["id"],))["provider"])
    assert [c["clip"] for c in note["clips"]] == [1, 2] and note["cost"] == 130   # both clips' cost
    item = db.one("SELECT * FROM generations WHERE job_id = ?", (ended["id"],))
    assert item["kind"] == "video" and item["filename"].endswith(".mp4")
    assert client.app.state.router.running == {}

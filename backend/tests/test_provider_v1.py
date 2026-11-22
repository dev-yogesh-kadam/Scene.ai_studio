"""The Scene Provider API v1 adapter (providers/v1.py) against a fake v1 server (fake_v1.py), and a job made through it
(jobs._run_provider): offered, made, filed, failed over, chained; and a job of an old ComfyUI workflow, which fails at
once. Each job test adds its own provider (no_models): the test studio's is studio_models.py's."""

import asyncio
import json
import time
from pathlib import Path

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
        # queued again because the provider was not ready: a new request (new uploads), so a key of its own
        assert v1.idempotency_key(9, attempt=1) == "scene-job-9-try-1"
        assert v1.idempotency_key(9, clip=2, attempt=2) == "scene-job-9-clip-2-try-2"
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


@pytest.mark.no_models
def test_a_providers_model_is_offered_made_and_filed(client, monkeypatch):
    fake = FakeV1()
    desk, _ = a_provider(client, monkeypatch, fake)
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


@pytest.mark.no_models
def test_a_test_key_stops_at_the_providers_quote_and_the_credits_come_back(client, monkeypatch):
    fake = FakeV1()
    desk, _ = a_provider(client, monkeypatch, fake, secret="sa_test_beta5678")
    _, roles = prompt_of(client)
    before = client.get("/api/auth/me").json()["credits"]
    job_id = client.post("/api/jobs", data={"settings": json.dumps(dict(SEEDANCE_JOB, values={roles["prompt"]: "a cat"}))}).json()["id"]
    ended = wait_for(client, job_id)
    assert ended["status"] == "failed" and ended["error"].startswith("The provider: Test mode: would cost 65 credits")
    assert client.get("/api/auth/me").json()["credits"] == before


@pytest.mark.no_models
def test_a_revoked_key_fails_over_to_the_next_key_and_is_shown_invalid(client, monkeypatch):
    fake = FakeV1(live=("sa_live_alpha1234", "sa_live_gamma9999"))
    desk, added = a_provider(client, monkeypatch, fake)
    provider_id = added["provider_id"]
    desk.post("/api/admin/providers/keys", json={"provider_id": provider_id, "secret": "sa_live_gamma9999", "label": "studio B"})
    fake.revoked.add("sa_live_alpha1234")   # revoked in Studio_automation's panel
    _, roles = prompt_of(client)
    job_id = client.post("/api/jobs", data={"settings": json.dumps(dict(SEEDANCE_JOB, values={roles["prompt"]: "a cat"}))}).json()["id"]
    assert wait_for(client, job_id)["status"] == "done"
    assert [c["last4"] for c in fake.calls if c["path"] in ("/v1/jobs",)] == ["1234", "9999"]
    keys = {k["label"]: k for k in next(p for p in desk.get("/api/admin/providers").json()["providers"] if p["id"] == provider_id)["keys"]}
    assert keys["studio A"]["status"] == "invalid" and "revoked" in keys["studio A"]["last_error"]
    assert json.loads(client.app.state.db.one("SELECT provider FROM jobs WHERE id = ?", (job_id,))["provider"])["key"] == "studio B"


@pytest.mark.no_models
def test_with_no_key_for_a_model_the_job_fails_at_once_and_its_credits_come_back(client, monkeypatch):
    fake = FakeV1()
    desk, added = a_provider(client, monkeypatch, fake)
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


# ---------------------------------------------------------------- a job of a ComfyUI workflow

def test_a_job_of_an_old_comfyui_workflow_fails_at_once(client):
    """A job still queued from before ComfyUI went (its workflow a file's, not a model's) is never sent anywhere."""
    from scene import jobs
    me = register(client)
    manager = client.app.state.jobs
    job_id = manager.add(me["id"], "old shot", "video/h3_all_in_one", {"workflow": "video/h3_all_in_one", "values": {}}, "", 60, 0)
    ended = wait_for(client, job_id)
    assert ended["status"] == "failed" and ended["error"] == jobs.NOT_A_MODEL.format("video/h3_all_in_one")
    assert not [c for c in client.provider.calls if c["path"] == "/v1/jobs"]   # nothing reached a provider


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


@pytest.mark.no_models
def test_a_long_video_is_chained_clip_by_clip_on_the_providers_model(client, monkeypatch):
    fake = FakeV1()
    fake.output = tiny_mp4()
    desk, _ = a_provider(client, monkeypatch, fake)
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


# ---------------------------------------------------------------- Studio_automation's sound tools: several outputs a job

def sound_provider(client, monkeypatch):
    from fake_v1 import SEPARATE_VOICE, SEEDANCE, SPEECH, TRANSCRIBE, TRANSCRIBE_VIDEO
    fake = FakeV1(models=(SEEDANCE, SPEECH, TRANSCRIBE, TRANSCRIBE_VIDEO, SEPARATE_VOICE))
    a_provider(client, monkeypatch, fake)
    return fake


def a_sound_job(client, workflow, name, data=b"a voice over music"):
    from scene.references import keep_reference
    me = client.get("/api/auth/me").json()["id"]
    kept = asyncio.run(keep_reference(client.app.state.jobs.storage, "vo.wav", data, db=client.app.state.db, user_id=me))
    schema = client.get("/api/workflows/" + workflow).json()
    refs = {r["id"]: {"comfy_name": kept, "name": "vo"} for r in schema["refs"] if not r["optional"]}
    made = client.post("/api/jobs", data={"settings": json.dumps({"workflow": workflow, "values": {}, "refs": refs, "name": name})})
    assert made.status_code == 200, made.text
    ended = wait_for(client, made.json()["id"])
    assert ended["status"] == "done", ended
    rows = client.app.state.db.all("SELECT * FROM generations WHERE job_id = ? ORDER BY id", (ended["id"],))
    return ended, rows


@pytest.mark.no_models
def test_studio_automations_transcript_is_filed_as_text_twice_labelled_and_reads_as_on_this_pcs(client, monkeypatch):
    from scene import film, transcript
    fake = sound_provider(client, monkeypatch)
    listed = {w["id"] for w in client.get("/api/workflows").json()["workflows"]}
    assert {"audio/@transcribe", "audio/@transcribe_video", "audio/@separate_voice"} <= listed
    ended, rows = a_sound_job(client, "audio/@transcribe", "VO")
    sent = next(c for c in fake.calls if c["path"] == "/v1/jobs")
    assert sent["body"]["model"] == "transcribe" and sent["body"]["input"]["audio"].startswith("file_")
    provider_job = next(iter(fake.jobs))
    assert b"a voice over music" in fake.files[sent["body"]["input"]["audio"]]   # the multipart body the fake keeps
    assert [c["path"] for c in fake.calls if "/outputs/" in c["path"]] == [
        "/v1/jobs/{}/outputs/{}".format(provider_job, n) for n in (0, 1)]
    assert [(r["kind"], r["name"], Path(r["filename"]).suffix) for r in rows] == [
        ("text", "VO · transcript", ".json"), ("text", "VO · subtitles", ".srt")]
    assert [json.loads(r["context"])["output"] for r in rows] == ["transcript", "subtitles"]
    # usable as On this PC's was: the agent's transcript tool and the subtitles read it (transcript.parse), and its
    # words' times light the karaoke subtitles (film.words_for, the edits' words_from)
    folder = client.app.state.outputs.folder(rows[0]["user_id"])
    texts = [(folder / r["filename"]).read_text(encoding="utf-8") for r in rows]
    from_json, from_srt = transcript.parse(texts[0]), transcript.parse(texts[1])
    assert [l["text"] for l in from_json] == [l["text"] for l in from_srt] == ["Hello there"]
    assert from_json[0]["end"] == from_srt[0]["end"] == 1.2 and from_json[0]["speaker"] == "SPEAKER_00"
    assert film.words_for(from_json, texts[0])
    assert client.app.state.router.running == {}


@pytest.mark.no_models
def test_studio_automations_voice_separation_files_the_voice_and_the_music_as_sounds(client, monkeypatch):
    sound_provider(client, monkeypatch)
    _, rows = a_sound_job(client, "audio/@separate_voice", "Street")
    assert [(r["kind"], r["name"], Path(r["filename"]).suffix) for r in rows] == [
        ("audio", "Street · voice", ".wav"), ("audio", "Street · music_fx", ".wav")]
    folder = client.app.state.outputs.folder(rows[0]["user_id"])
    assert [(folder / r["filename"]).read_bytes() for r in rows] == [b"just the voice", b"just the music"]


def test_an_outputs_kind_ending_and_label_hold_without_its_name():
    from scene import jobs
    assert jobs._suffix_of_output({"mime": "application/json; charset=utf-8"}) == ".json"
    assert jobs._suffix_of_output({"mime": "application/x-subrip"}) == ".srt"
    assert jobs._suffix_of_output({"name": "Voice.WAV"}) == ".wav"
    assert jobs._label_of_output({"name": "transcript.srt"}, ".srt") == "subtitles"
    assert jobs._label_of_output({"name": "music_fx.wav"}, ".wav") == "music_fx"
    assert jobs._label_of_output({"type": "audio"}, ".wav") == "audio"
    assert jobs._kind_of_output({"type": "subtitles"}, ".srt") == "text"   # a type the studio does not know: by its ending

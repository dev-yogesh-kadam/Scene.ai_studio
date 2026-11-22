"""A voice track with music or noise under it: the voice is taken out first (jobs._clean_voice_here) by whichever
provider offers separate_voice through the router (Studio_automation's key; On this PC where it is set up), and the
provider's lip sync follows it alone. (ComfyUI's own separation went with ComfyUI.)"""

import asyncio

import pytest

from fake_v1 import SEPARATE_VOICE, FakeV1
from scene.providers import registry, v1
from test_provider_v1 import a_provider

from scene import agent


def test_the_agent_is_offered_clean_voice_only_where_lips_follow_a_track():
    base = {"id": "video/x", "title": "X", "description": "", "refs": [], "options": [],
            "controls": [{"id": "1:text", "role": "prompt", "type": "text", "default": ""}]}
    assert "3:audio" in agent.offer(dict(base, slots={"voice_track": "3:audio"}))["clean_voice"]
    assert "clean_voice" not in agent.offer(dict(base, slots={}))
    assert agent.reply_format(["video/x"])["properties"]["steps"]["items"]["properties"]["clean_voice"] == {"type": "boolean"}


# ---------------------------------------------------------------- a provider's lip sync: its voice separated first

LIP_SYNC = {"model_id": "lip_sync", "name": "Lip sync", "capability": "lip_sync", "best_for": "",
            "input_schema": {"type": "object", "required": ["video", "audio"], "properties": {
                "video": {"type": "string", "x-file": "video"}, "audio": {"type": "string", "x-file": "audio"}}},
            "limits": {}, "pricing": {"unit": "job", "credits": None}}
NO_CLEAN_VOICE = ("The voice can't be taken out of the music: voice separation is not set up on this PC. Make it without "
                  "that, or set it up (docs/servers.md).")


@pytest.fixture(autouse=True)
def quick_polls(monkeypatch):
    monkeypatch.setattr(v1, "POLL_FIRST", 0.01)
    monkeypatch.setattr(v1, "POLL_MOST", 0.02)


def provider_job(client, monkeypatch, offers=True):
    """A lip sync's workflow, its voice track kept, and (when `offers`) Studio_automation offering separate_voice. On
    this PC is not offered: the test studio's tools' Python is not there (conftest), as on Zoro."""
    from scene.providers import workflows as provider_workflows
    from scene.references import keep_reference
    fake = FakeV1(models=(SEPARATE_VOICE,) if offers else ())
    if offers:
        a_provider(client, monkeypatch, fake)
    jobs = client.app.state.jobs
    mix = asyncio.run(keep_reference(jobs.storage, "street.wav", b"voice and music"))
    wf = provider_workflows.build(LIP_SYNC)
    slot = next(r for r in wf["profile"]["required_refs"] if r.endswith(":audio"))
    return fake, jobs, wf, slot, mix


def sent_jobs(fake):
    return [c for c in fake.calls if c["path"] == "/v1/jobs"]


@pytest.mark.no_models
def test_a_lip_syncs_voice_is_separated_by_the_provider_the_router_picks(client, monkeypatch):
    from scene.references import REFERENCES
    fake, jobs, wf, slot, mix = provider_job(client, monkeypatch)
    job = {"id": 9, "user_id": 1, "name": "Talk", "settings": {"clean_voice": True, "refs": {slot: {"comfy_name": mix, "name": "street"}}}}
    live = {}
    settings = asyncio.run(jobs._clean_voice_here(job, live, wf))
    (sent,) = sent_jobs(fake)
    assert sent["body"]["model"] == "separate_voice" and sent["idempotency"] == "scene-job-9-clean-voice"
    assert b"voice and music" in fake.files[sent["body"]["input"]["audio"]]
    voice = settings["refs"][slot]["comfy_name"]
    assert voice != mix and jobs.storage.read_bytes(REFERENCES, voice) == b"just the voice"   # the voice, not music_fx
    assert settings["refs"][slot]["name"] == "the voice of street"
    assert job["settings"]["refs"][slot]["comfy_name"] == mix   # the job keeps its own track
    assert client.app.state.router.running == {} and live["node"] == ""   # the key let go once the voice was in


@pytest.mark.no_models
def test_with_no_provider_offering_separation_the_job_is_refused_in_the_same_words(client, monkeypatch):
    from scene.providers.base import RequestProblem
    fake, jobs, wf, slot, mix = provider_job(client, monkeypatch, offers=False)
    db = client.app.state.db
    # On this PC's models cached from a database made where it ran (LUFI's, copied to Zoro): not offered here, not used
    registry.seed(db, client.app.state.settings)
    local = next(p for p in registry.providers(db) if p["kind"] == "local_tools")
    key = registry.keys(db, local["id"])[0]
    registry.save_models(db, local["id"], key["id"], [{"id": "separate_voice", "name": "Separate voice", "capability": "separate_voice"}])
    db.run("UPDATE provider_keys SET status = 'ok' WHERE id = ?", (key["id"],))
    client.app.state.router.forget()
    plain = {"refs": {slot: {"comfy_name": mix}}}
    assert asyncio.run(jobs._clean_voice_here({"id": 1, "user_id": 1, "name": "x", "settings": plain}, {}, wf)) is plain
    asked = {"id": 2, "user_id": 1, "name": "x", "settings": {"clean_voice": True, "refs": {slot: {"comfy_name": mix}}}}
    with pytest.raises(RequestProblem) as refused:
        asyncio.run(jobs._clean_voice_here(asked, {}, wf))
    assert str(refused.value) == NO_CLEAN_VOICE
    assert client.app.state.router.running == {}


@pytest.mark.no_models
def test_nothing_is_separated_unless_asked_and_there_is_a_voice_track(client, monkeypatch):
    from scene.providers import workflows as provider_workflows
    from studio_models import MODELS
    fake, jobs, wf, slot, mix = provider_job(client, monkeypatch)
    upscale = provider_workflows.build(dict(next(m for m in MODELS if m["id"] == "upscale_video"), model_id="upscale_video"))
    for settings, workflow in [({"refs": {slot: {"comfy_name": mix}}}, wf),                       # not asked
                               ({"clean_voice": True, "refs": {"2:video": {"comfy_name": mix}}}, upscale),   # no voice track
                               ({"clean_voice": True, "refs": {}}, wf)]:                           # the track not given
        job = {"id": 1, "user_id": 1, "name": "x", "settings": settings}
        assert asyncio.run(jobs._clean_voice_here(job, {}, workflow)) is settings
    assert not sent_jobs(fake)


@pytest.mark.no_models
def test_the_separation_runs_on_the_key_the_lip_sync_holds_when_it_is_the_only_one(client, monkeypatch):
    """One Studio_automation key, one job at a time, held by the lip sync itself: the separation runs on it first
    rather than waiting for the key the job holds."""
    import time
    from scene.references import REFERENCES
    fake, jobs, wf, slot, mix = provider_job(client, monkeypatch)
    router, db = client.app.state.router, client.app.state.db
    db.run("UPDATE provider_keys SET max_concurrent = 1")
    router.forget()
    held, _ = router.pick("separate_voice")
    router.take(held, 9)   # the queue took it for job 9
    job = {"id": 9, "user_id": 1, "name": "Talk", "choice": held,
           "settings": {"clean_voice": True, "refs": {slot: {"comfy_name": mix, "name": "street"}}}}
    started = time.time()
    settings = asyncio.run(asyncio.wait_for(jobs._clean_voice_here(job, {}, wf), 20))
    assert time.time() - started < 10 and len(sent_jobs(fake)) == 1
    assert jobs.storage.read_bytes(REFERENCES, settings["refs"][slot]["comfy_name"]) == b"just the voice"
    assert router.running == {held["key"]["id"]: {9}}   # still the job's, for its lip sync

"""A voice track with music or noise under it: the voice is taken out first, on this PC (providers/local.py, through
jobs._clean_voice_here), and the provider's lip sync follows it alone. (ComfyUI's own separation went with ComfyUI.)"""

import asyncio

from scene import agent


def test_the_agent_is_offered_clean_voice_only_where_lips_follow_a_track():
    base = {"id": "video/x", "title": "X", "description": "", "refs": [], "options": [],
            "controls": [{"id": "1:text", "role": "prompt", "type": "text", "default": ""}]}
    assert "3:audio" in agent.offer(dict(base, slots={"voice_track": "3:audio"}))["clean_voice"]
    assert "clean_voice" not in agent.offer(dict(base, slots={}))
    assert agent.reply_format(["video/x"])["properties"]["steps"]["items"]["properties"]["clean_voice"] == {"type": "boolean"}


# ---------------------------------------------------------------- a provider's lip sync: separated on this PC (local.py)

LIP_SYNC = {"model_id": "lip_sync", "name": "Lip sync", "capability": "lip_sync", "best_for": "",
            "input_schema": {"type": "object", "required": ["video", "audio"], "properties": {
                "video": {"type": "string", "x-file": "video"}, "audio": {"type": "string", "x-file": "audio"}}},
            "limits": {}, "pricing": {"unit": "job", "credits": None}}


class FakeTools:
    def __init__(self, ready=True):
        self.ready, self.ran = ready, []

    async def installed(self):
        return {"separate_voice": {"ready": self.ready, "why": "" if self.ready else "not installed"}}

    async def run_now(self, model, input, label=""):
        from pathlib import Path
        self.ran.append((model, Path(input["audio"]).read_bytes()))
        voice = Path(input["audio"]).with_name("voice.wav")
        voice.write_bytes(b"just the voice")
        return {"voice.wav": str(voice)}


def provider_job(client, monkeypatch, tools):
    from scene.providers import router as provider_router, workflows as provider_workflows
    from scene.references import keep_reference
    monkeypatch.setattr(provider_router, "local_tools", lambda settings: tools)
    jobs = client.app.state.jobs
    mix = asyncio.run(keep_reference(jobs.storage, "street.wav", b"voice and music"))
    wf = provider_workflows.build(LIP_SYNC)
    slot = next(r for r in wf["profile"]["required_refs"] if r.endswith(":audio"))
    return jobs, wf, slot, mix


def test_a_providers_lip_sync_gets_the_voice_separated_on_this_pc(client, monkeypatch):
    from scene.references import REFERENCES
    tools = FakeTools()
    jobs, wf, slot, mix = provider_job(client, monkeypatch, tools)
    job = {"id": 9, "user_id": 1, "name": "Talk", "settings": {"clean_voice": True, "refs": {slot: {"comfy_name": mix, "name": "street"}}}}
    settings = asyncio.run(jobs._clean_voice_here(job, {}, wf))
    assert tools.ran == [("separate_voice", b"voice and music")]
    voice = settings["refs"][slot]["comfy_name"]
    assert voice != mix and jobs.storage.read_bytes(REFERENCES, voice) == b"just the voice"
    assert job["settings"]["refs"][slot]["comfy_name"] == mix   # the job keeps its own track


def test_a_providers_job_is_left_as_it_is_unless_asked_and_refused_when_nothing_can_separate(client, monkeypatch):
    import pytest
    from scene.providers.base import RequestProblem
    tools = FakeTools(ready=False)
    jobs, wf, slot, mix = provider_job(client, monkeypatch, tools)
    plain = {"refs": {slot: {"comfy_name": mix}}}
    assert asyncio.run(jobs._clean_voice_here({"id": 1, "user_id": 1, "name": "x", "settings": plain}, {}, wf)) is plain
    asked = {"id": 2, "user_id": 1, "name": "x", "settings": {"clean_voice": True, "refs": {slot: {"comfy_name": mix}}}}
    with pytest.raises(RequestProblem, match="not set up"):
        asyncio.run(jobs._clean_voice_here(asked, {}, wf))
    assert not tools.ran


def test_nothing_is_separated_unless_asked_and_there_is_a_voice_track(client, monkeypatch):
    from scene.providers import workflows as provider_workflows
    from studio_models import MODELS
    tools = FakeTools()
    jobs, wf, slot, mix = provider_job(client, monkeypatch, tools)
    upscale = provider_workflows.build(dict(next(m for m in MODELS if m["id"] == "upscale_video"), model_id="upscale_video"))
    for settings, workflow in [({"refs": {slot: {"comfy_name": mix}}}, wf),                       # not asked
                               ({"clean_voice": True, "refs": {"2:video": {"comfy_name": mix}}}, upscale),   # no voice track
                               ({"clean_voice": True, "refs": {}}, wf)]:                           # the track not given
        job = {"id": 1, "user_id": 1, "name": "x", "settings": settings}
        assert asyncio.run(jobs._clean_voice_here(job, {}, workflow)) is settings
    assert not tools.ran

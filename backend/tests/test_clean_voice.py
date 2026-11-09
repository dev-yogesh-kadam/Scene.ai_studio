"""A voice track with music or noise under it: the voice is taken out first, and the lips follow it alone."""

import asyncio

from scene import agent


def stubbed(jobs):
    """The job manager with ComfyUI stubbed: every render is a voice separation that saves both stems."""
    calls, uploads = [], []

    class Comfy:
        async def upload(self, name, data, mime, subfolder=""):
            uploads.append((name, data))
            return name

    async def render(job, live, wf, settings, client_id):
        calls.append((wf["id"], settings))
        return {"outputs": {"3": {"audio": [{"filename": "voice_stem.wav", "type": "output"}]},
                            "4": {"audio": [{"filename": "music_fx_stem.wav", "type": "output"}]}}}, {}

    async def fetch(item, target, kind="output", comfy=None):
        target.write_bytes(item["filename"].encode())

    jobs._render, jobs._fetch = render, fetch
    return calls, uploads, {"comfy": Comfy()}


def test_the_voice_stem_goes_in_the_voice_track(client):
    jobs = client.app.state.jobs
    calls, uploads, live = stubbed(jobs)
    mix = {"comfy_name": "scene_mix.wav", "name": "street interview"}
    job = {"id": 7, "user_id": 1, "name": "Talk", "settings": {"clean_voice": True, "refs": {"3:audio": mix}}}
    settings = asyncio.run(jobs._clean_voice(job, live, {"slots": {"voice_track": "3:audio"}}, "c"))
    assert calls[0][0] == "audio/audio_separate_voice" and list(calls[0][1]["refs"].values()) == [mix]
    assert uploads == [("scene_voice_7.wav", b"voice_stem.wav")]   # the voice stem, not the music and effects
    assert settings["refs"]["3:audio"]["comfy_name"] == "scene_voice_7.wav"
    assert job["settings"]["refs"]["3:audio"] == mix   # the job keeps its own track: made again, it is cleaned again


def test_nothing_is_separated_unless_asked_and_there_is_a_voice_track(client):
    jobs = client.app.state.jobs
    calls, _, live = stubbed(jobs)
    refs = {"3:audio": {"comfy_name": "scene_mix.wav"}}
    for settings, schema in [({"refs": refs}, {"slots": {"voice_track": "3:audio"}}),
                             ({"clean_voice": True, "refs": refs}, {"slots": {}}),
                             ({"clean_voice": True, "refs": {}}, {"slots": {"voice_track": "3:audio"}})]:
        assert asyncio.run(jobs._clean_voice({"id": 1, "user_id": 1, "name": "x", "settings": settings}, live, schema, "c")) is settings
    assert not calls


def test_the_agent_is_offered_clean_voice_only_where_lips_follow_a_track():
    base = {"id": "video/x", "title": "X", "description": "", "refs": [], "options": [],
            "controls": [{"id": "1:text", "role": "prompt", "type": "text", "default": ""}]}
    assert "3:audio" in agent.offer(dict(base, slots={"voice_track": "3:audio"}))["clean_voice"]
    assert "clean_voice" not in agent.offer(dict(base, slots={}))
    assert agent.reply_format(["video/x"])["properties"]["steps"]["items"]["properties"]["clean_voice"] == {"type": "boolean"}

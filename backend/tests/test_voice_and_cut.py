"""A voiceover always goes with a voice, and the final cut joins any mix of cuts and crossfades (22 Nov 2026).

None of these need the test database: run alone with `pytest tests/test_voice_and_cut.py --noconftest`."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from scene import jobs, media
from scene.plans import cut_not_ready
from scene.providers import base as provider_base, workflows as provider_workflows
from scene.providers.router import Router, language_tag

SPEECH = {"type": "object", "required": ["text"],
          "properties": {"text": {"type": "string", "maxLength": 2500}, "voice_id": {"type": "string", "maxLength": 200},
                         "language_code": {"type": "string", "maxLength": 20},
                         "style_instructions": {"type": "string", "maxLength": 4000}},
          "x-scene-order": ["text", "voice_id", "language_code", "style_instructions"]}
LIBRARY = [{"id": "v_us", "language": "en-US", "engine": "elevenlabs"}, {"id": "v_in", "language": "en-IN", "engine": "elevenlabs"},
           {"id": "v_hi", "language": "hi-IN", "engine": "gemini"}]


def speech_wf():
    return provider_workflows.build({"capability": "speech", "model_id": "speech", "name": "Speech", "input_schema": SPEECH,
                                     "limits": {}, "pricing": {}})


def router_with(voices):
    router = Router.__new__(Router)
    router._voices = {}

    async def listed(q="", language=""):
        return list(voices), ""
    router.voices = listed
    return router


# ---------------------------------------------------------------- languages and the provider's voices

@pytest.mark.parametrize("given, tag", [("English", "en-IN"), ("en", "en-IN"), ("EN_us", "en-US"), ("en-IN", "en-IN"),
                                        ("Hindi", "hi-IN"), ("hi", "hi-IN"), ("", ""), (None, ""), ("Klingon", "Klingon")])
def test_a_language_is_written_as_a_tag(given, tag):
    assert language_tag(given) == tag


def test_the_default_voice_fits_the_language_however_it_is_written():
    router = router_with(LIBRARY)
    picks = [asyncio.run(router.default_voice(lang)) for lang in ("English", "en", "en-IN", "en-GB", "hi", "ta-IN", "")]
    assert picks == ["v_in", "v_in", "v_in", "v_us", "v_hi", "v_us", "v_us"]
    assert asyncio.run(router_with([]).default_voice("en")) == ""


def test_a_voice_engine_is_read_from_the_voice_list():
    router = router_with(LIBRARY)
    router._voices = {("", ""): (0, LIBRARY, "")}
    assert asyncio.run(router.voice_engine("v_in")) == "elevenlabs"
    assert asyncio.run(router.voice_engine("v_hi")) == "gemini"
    assert asyncio.run(router.voice_engine("")) == ""


# ---------------------------------------------------------------- what a voiceover job sends

class Sent(Exception):
    """Raised where the job would reach the provider: carries what it would send."""


def manager(voices, before=""):
    """A JobManager with only what _provider_clip_once uses before it sends anything."""
    async def run(model, attempt, job_id=None, first=None):
        return await attempt({"provider": {}, "secret": "s"})

    async def files(adapter, secret, inputs):
        raise Sent(dict(inputs))
    router = router_with(voices)
    router.run = run
    router.adapter = lambda provider: None
    return SimpleNamespace(router=router, _voice_before=lambda job, wf: before, _who=lambda job: {},
                           notify=lambda user_id: None, _provider_files=files)


def sent(m, values):
    wf = speech_wf()
    job = {"id": "j1", "user_id": 1, "project_id": 5, "workflow": wf["id"], "settings": {}}
    with pytest.raises(Sent) as caught:
        asyncio.run(jobs.JobManager._provider_clip_once(m, job, {}, wf, {"values": values}))
    return caught.value.args[0]


def test_a_voiceover_with_no_voice_keeps_the_voice_its_module_used_last():
    got = sent(manager(LIBRARY, before="VCL_EARLIER"), {"2:value": "Hello", "4:value": "English"})
    assert got["voice_id"] == "VCL_EARLIER" and got["language_code"] == "en-IN"


def test_a_voiceover_with_no_voice_and_none_before_gets_the_providers_in_its_language():
    got = sent(manager(LIBRARY), {"2:value": "Hello", "4:value": "en"})
    assert got["voice_id"] == "v_in" and got["language_code"] == "en-IN"


def test_a_chosen_voice_is_sent_as_chosen():
    got = sent(manager(LIBRARY, before="VCL_EARLIER"), {"2:value": "Hello", "3:value": "v_hi", "4:value": "hi-IN"})
    assert got["voice_id"] == "v_hi"


def test_with_no_voice_anywhere_the_job_stops_here_with_a_clear_reason():
    with pytest.raises(provider_base.RequestProblem, match="No voice is chosen for this voiceover"):
        sent(manager([]), {"2:value": "Hello"})


def test_style_instructions_go_only_with_a_gemini_voice():
    m = manager(LIBRARY)
    m.router._voices = {("", ""): (0, LIBRARY, "")}
    assert "style_instructions" not in sent(m, {"2:value": "Hi", "3:value": "v_in", "5:value": "gentle"})
    assert sent(m, {"2:value": "Hi", "3:value": "v_hi", "5:value": "gentle"})["style_instructions"] == "gentle"


def test_the_voice_before_is_read_from_the_earlier_jobs_settings():
    wf = speech_wf()
    rows = [{"settings": json.dumps({"values": {"2:value": "Older", "3:value": ""}})},
            {"settings": json.dumps({"values": {"2:value": "Old", "3:value": "VCL_KEPT"}})}]
    m = SimpleNamespace(db=SimpleNamespace(all=lambda sql, params: rows))
    assert jobs.JobManager._voice_before(m, {"id": "j2", "user_id": 1, "project_id": 5, "workflow": wf["id"]}, wf) == "VCL_KEPT"
    assert jobs.JobManager._voice_before(m, {"id": "j2", "user_id": 1, "project_id": None, "workflow": wf["id"]}, wf) == ""


# ---------------------------------------------------------------- the final cut

def test_the_cut_names_every_shot_not_made():
    assert cut_not_ready(["Clip 2 the nap", "Clip 4 the finish"]) == \
        "Can't make the final cut yet: Clip 2 the nap and Clip 4 the finish aren't made. Make them again, then the cut."
    assert cut_not_ready(["Clip 2"]) == "Can't make the final cut yet: Clip 2 isn't made. Make it again, then the cut."


def test_a_failed_ffmpeg_says_its_cause_first():
    said = media.ffmpeg_said("\n".join(["Input #0, mov ...", "[Parsed_xfade_37 @ 0] Failed to configure output pad on Parsed_xfade_37",
                                        "[fc#0] Error reinitializing filters!"]
                                       + ["[aost#0:1/aac] Terminating thread with return code -22 (Invalid argument)"] * 3
                                       + ["[out#0/mp4] Nothing was written into output file"]))
    assert said.startswith("[Parsed_xfade_37 @ 0] Failed to configure output pad")
    assert "Nothing was written" in said


def _clip(path, seconds, sound_seconds=None):
    args = ["-f", "lavfi", "-i", "testsrc=d={}:s=320x180:r=24".format(seconds)]
    if sound_seconds:
        args += ["-f", "lavfi", "-i", "sine=d={}".format(sound_seconds), "-map", "0", "-map", "1", "-c:a", "aac"]
    asyncio.run(media._ffmpeg(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", path))
    return path


def test_the_cut_joins_cuts_and_crossfades_cards_and_short_sound(tmp_path):
    card = _clip(tmp_path / "card.mp4", 3)                  # a title or end card: no sound
    shot = _clip(tmp_path / "shot.mp4", 4, 4)
    short = _clip(tmp_path / "short.mp4", 5, 0.5)           # its sound ends long before its picture
    cases = [([card, short, shot, card], {1, 3}),           # Ember Fox's shape: a fade after a cut (it failed: xfade)
             ([short, shot, card], {2}), ([card, shot, shot, card], {1, 3}), ([shot, short, card], set()),
             ([shot, short, card, shot], {1, 2, 3})]
    for n, (clips, fades) in enumerate(cases):
        target = tmp_path / "cut{}.mp4".format(n)
        seconds = asyncio.run(media.sequence([(p, 0, 0) for p in clips], target, fades))
        found = asyncio.run(media.measure(target))
        assert abs(found["video_seconds"] - seconds) < 0.05 and abs(found["audio_seconds"] - seconds) < 0.05, (n, found)

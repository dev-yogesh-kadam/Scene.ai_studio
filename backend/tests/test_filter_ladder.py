"""A clip the provider's content filter flags goes up a ladder of tries; a clip made is never made again by a resume; the
final cut names every clip it lacks (22 Nov 2026).

None of these need the test database: run alone with `pytest tests/test_filter_ladder.py --noconftest`."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from scene import jobs, plans
from scene.jobs import JobManager
from scene.providers import base as provider_base, workflows as provider_workflows

VIDEO = {"type": "object",
         "properties": {"prompt": {"type": "string"}, "duration": {"type": "integer", "default": 5, "minimum": 4, "maximum": 15},
                        "sound": {"type": "boolean", "default": False},
                        "aspect_ratio": {"type": "string", "enum": ["16:9", "21:9", "9:16"]},
                        "reference_images": {"type": "array", "items": {"type": "string", "x-file": "image"}}},
         "x-scene-order": ["prompt", "duration", "sound", "aspect_ratio", "reference_images"]}
STAND_IN = dict(VIDEO, properties=dict(VIDEO["properties"], aspect_ratio={"type": "string", "enum": ["16:9", "9:16"]}))
FLAG = "The provider could not make the clip: The generated video was flagged by the content filter. (credits refunded)."


def video_wf(model_id="seedance_2_5", schema=VIDEO):
    return provider_workflows.build({"capability": "text_to_video", "model_id": model_id, "name": model_id,
                                     "input_schema": schema, "limits": {}, "pricing": {}})


def manager(outcomes, offered=("seedance_2_0",)):
    """A JobManager whose single tries come out as `outcomes` says, one a try: "flag", "other" or "ok". Each try's
    (rung, sound_off, model) is kept in .tries."""
    m = SimpleNamespace(tries=[], notify=lambda user_id: None)
    left = list(outcomes)

    async def once(job, live, wf, settings, clip=None, plain=False, rung=0, sound_off=False, model=None):
        m.tries.append((rung, sound_off, model))
        outcome = left.pop(0)
        if outcome == "flag":
            raise provider_base.RequestProblem(FLAG)
        if outcome == "other":
            raise provider_base.RequestProblem("The prompt is too long.")
        return ("made", {}), {}

    async def load(wid):
        model = provider_workflows.model_id_of(wid)
        if model not in offered:
            raise LookupError(wid)
        return video_wf(model, STAND_IN)
    m._provider_clip_once = once
    m.catalog = SimpleNamespace(load=load)
    m._next_rung = lambda *a: JobManager._next_rung(m, *a)
    m._stand_in = lambda *a: JobManager._stand_in(m, *a)
    return m


def run(m, sound="on"):
    settings = {"values": {"2:value": "A fox talks to a rabbit"}, "options": {"sound": sound}}
    return asyncio.run(JobManager._provider_clip(m, {"id": "j1", "user_id": 1, "name": "Clip 4 the finish"}, {}, video_wf(), settings))


def test_a_flagged_clip_is_tried_again_as_it_was_first():
    m = manager(["flag", "ok"])
    (made, ctx) = run(m)
    assert m.tries == [(0, False, None), (1, False, None)] and "content_filter" not in ctx


def test_the_ladder_goes_same_same_then_without_sound_then_on_a_stand_in():
    m = manager(["flag", "flag", "flag", "flag", "ok"])
    _, ctx = run(m)
    assert m.tries == [(0, False, None), (1, False, None), (2, False, None), (3, True, None), (4, True, "seedance_2_0")]
    assert "without its sound" in ctx["content_filter"] and "seedance_2_0" in ctx["content_filter"]


def test_made_without_sound_says_so_for_the_voiceover():
    m = manager(["flag", "flag", "flag", "ok"])
    _, ctx = run(m)
    assert m.tries[-1] == (3, True, None) and "voiceover" in ctx["content_filter"]


def test_a_clip_without_sound_skips_that_rung():
    m = manager(["flag", "flag", "flag", "ok"])
    run(m, sound="off")
    assert m.tries[-1] == (4, False, "seedance_2_0")


def test_after_the_last_rung_it_fails_saying_what_was_tried():
    m = manager(["flag"] * 5)
    with pytest.raises(provider_base.RequestProblem) as caught:
        run(m)
    said = str(caught.value)
    assert "flagged “Clip 4 the finish” on every try" in said and "3 tries as it was" in said
    assert "one without sound" in said and "seedance_2_0" in said and len(m.tries) == 5


def test_with_no_stand_in_offered_it_stops_after_the_sound_rung():
    m = manager(["flag"] * 4, offered=())
    with pytest.raises(provider_base.RequestProblem, match="on every try"):
        run(m)
    assert len(m.tries) == 4


def test_another_failure_is_not_tried_again():
    m = manager(["other"])
    with pytest.raises(provider_base.RequestProblem, match="too long"):
        run(m)
    assert len(m.tries) == 1


def test_only_the_content_filter_is_flagged():
    assert jobs.flagged(provider_base.RequestProblem(FLAG))
    assert jobs.flagged(provider_base.RequestProblem("Refused.", code="content_filter"))
    assert not jobs.flagged(provider_base.RequestProblem("The prompt is too long."))


def test_a_stand_in_takes_only_what_it_offers():
    m = manager([])
    m._inputs_for = lambda *a: JobManager._inputs_for(m, *a)
    given = {"prompt": "A fox", "duration": 5, "sound": False, "aspect_ratio": "21:9", "seed": 3,
             "reference_images": [{"file": "a"}, {"file": "b"}]}
    kept = asyncio.run(m._inputs_for("seedance_2_0", "text_to_video", given))
    assert kept == {"prompt": "A fox", "duration": 5, "sound": False, "reference_images": [{"file": "a"}, {"file": "b"}]}


# ---------------------------------------------------------------- a clip made is never made again

class Rows:
    """The jobs table as _finished asks it: (plan, step) -> (job, item) of a finished job."""
    def __init__(self, done):
        self.done = done

    def one(self, sql, params):
        hit = self.done.get(tuple(params))
        return {"job": hit[0], "item": hit[1]} if hit else None

    async def aone(self, sql, params):
        return {"status": "failed"}   # every job the progress points at failed


def test_a_resume_marks_a_step_made_by_a_job_its_progress_lost():
    runner = SimpleNamespace(db=Rows({(7, 1): ("job149", 55)}))
    runner._finished = lambda plan_id, step: plans.PlanRunner._finished(runner, plan_id, step)
    progress = [{"job": "job145", "error": "Not made (failed)."}, {"job": "job148", "error": "Not made (failed)."}]
    again = asyncio.run(plans.PlanRunner._again(runner, progress, 7))
    assert again == [0]   # Clip 4 (step 1) is not sent again: its job149 finished
    assert progress[1] == {"job": "job149", "made": 55, "error": ""}


# ---------------------------------------------------------------- the final cut names what it lacks

def test_the_cut_names_every_clip_it_lacks(tmp_path):
    from scene import edits, media
    there = tmp_path / "shot1.mp4"
    there.write_bytes(b"x")

    def item(item_id, kind="video"):
        if item_id != 1:
            raise media.MediaError("A video this was to be made from is no longer in the library.")
        return there
    settings = {"clips": [{"id": 1, "name": "Clip 1"}, {"id": 2, "name": "Clip 2 the nap"}, {"id": 3, "name": "Clip 4 the finish"}]}
    with pytest.raises(media.MediaError, match="Clip 2 the nap and Clip 4 the finish aren't made"):
        asyncio.run(edits._assemble(settings, item, tmp_path / "cut.mp4", "", None))

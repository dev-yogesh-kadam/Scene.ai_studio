"""Craft skills v2 on the providers' models (20 November 2026): every video model of script-to-video's table has its
prompter here, a model's own prompt length reaches the agent, and a job whose reference videos a model can't take (how
many, their seconds each and together) is refused before it is charged, with what to do."""

import json
import re

import pytest

from scene import skills
from scene.api import studio
from scene.comfy import workflows
from scene.providers import workflows as provider_workflows
from test_api import register

TABLE_ROW = re.compile(r"^\| (`[^|]+`) \| (craft-prompter-[\w-]+) \| ([^|]+) \|$", re.M)


def test_every_video_model_in_the_table_has_its_prompter_and_chain_only_where_v2_offers_it():
    rows = TABLE_ROW.findall(skills.find("script-to-video")["text"])
    assert len(rows) == 4
    for models, prompter, methods in rows:
        found = skills.find(prompter)
        assert found and found["craft"] and found["id"] == skills.canonical(prompter), prompter
        ids = re.findall(r"`([\w.]+)`", models)
        assert all(i in found["text"] for i in ids[:1]), (prompter, ids)
        assert ("Chain" in methods) == (ids[0] in ("seedance_2_5", "wan_3_0")), (ids, methods)
    for sid in ("prompter-seedance-2-5", "prompter-seedance-2", "prompter-wan-3"):
        assert "## Studio: " in skills.find(sid)["text"] and "reference audio slot" in skills.find(sid)["text"]


SEEDANCE = {"model_id": "seedance_x", "name": "Seedance X", "capability": "text_to_video", "best_for": "",
            "input_schema": {"type": "object", "required": [], "properties": {
                "prompt": {"type": "string", "maxLength": 10000},
                "duration": {"type": "integer", "minimum": 4, "maximum": 15},
                "reference_video": {"type": "string", "x-file": "video"},
                "reference_videos": {"type": "array", "maxItems": 2, "items": {"type": "string", "x-file": "video"}}}},
            "limits": {"seconds": {"min": 4, "max": 15}, "max_reference_videos": 2,
                       "reference_clips": {"max_clips": 3, "seconds_each": [1.8, 15.2], "seconds_together": 15.2}},
            "pricing": {"unit": "second", "credits": 10}}


def test_a_models_own_prompt_length_reaches_its_schema():
    schema = workflows.describe(provider_workflows.build(SEEDANCE))
    assert schema["prompt_chars"] == 10000
    plain = dict(SEEDANCE, input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}})
    assert workflows.describe(provider_workflows.build(plain))["prompt_chars"] == 0


def test_reference_videos_over_the_models_count_or_seconds_are_refused_with_what_to_do():
    wf = provider_workflows.build(SEEDANCE)
    schema = workflows.describe(wf)
    videos = [r["id"] for r in schema["refs"] if r["kind"] == "video"]
    assert len(videos) == 3   # the Reference video and two more
    given = lambda slots: {"refs": {s: {"comfy_name": s + ".mp4"} for s in slots}}
    problem = provider_workflows.limits_problem
    assert "at most 2 reference videos; this job gives 3" in problem(wf, schema, given(videos))
    assert problem(wf, schema, given(videos[:2]), {videos[0]: 8, videos[1]: 7}) == ""
    each = problem(wf, schema, given(videos[:1]), {videos[0]: 20})
    assert "1.8 to 15.2 seconds; one here is 20.0 s" in each and "-sseof" in each
    together = problem(wf, schema, given(videos[:2]), {videos[0]: 10, videos[1]: 9})
    assert "15.2 seconds of reference video in all; this job gives 19.0 s" in together
    assert problem(wf, schema, given(videos[:1])) == ""   # not measured: the provider says


def test_a_job_with_a_clip_too_long_for_the_reference_video_slot_is_refused_before_it_is_charged(client, monkeypatch):
    register(client)
    schema = client.get("/api/workflows/video/@seedance_2_5").json()
    slot = next(r["id"] for r in schema["refs"] if r["kind"] == "video")
    prompt = next(c["id"] for c in schema["controls"] if c["role"] == "prompt")

    async def measured(state, data, filename):
        return 31.0
    monkeypatch.setattr(studio, "_video_seconds", measured)
    sent = client.post("/api/jobs", data={"settings": json.dumps({"workflow": "video/@seedance_2_5", "values": {prompt: "She walks on."}, "options": {}})},
                       files={"ref:" + slot: ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")})
    assert sent.status_code == 400 and "1.8 to 30 seconds; one here is 31.0 s" in sent.json()["detail"]

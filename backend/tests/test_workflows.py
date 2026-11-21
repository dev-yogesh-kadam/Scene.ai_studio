"""The studio's workflow format (comfy/workflows.py), which every provider model is offered in (providers/workflows.py):
its form, its choices written into the model's input, a long video's clips, estimates, sizes and the media helpers.

(Reading and converting ComfyUI workflow files, their subgraphs, dynamic combos and node lists, and the presets of the
ComfyUI workflows went with ComfyUI on 18 November.)"""

import asyncio

import pytest

from scene.comfy import workflows
from scene.providers.workflows import provider_input
from test_picture_refs import load

PROMPT, DURATION = "2:value", "3:value"   # Seedance's prompt and length (the provider form's first nodes)


def seedance():
    wf = load("seedance_2_5")
    return wf, workflows.describe(wf)


def test_a_models_form_has_its_prompt_length_choices_and_frames():
    wf, schema = seedance()
    assert schema["id"] == "video/@seedance_2_5" and schema["source"] == "generation"
    assert {c["role"] for c in schema["controls"]} == {"prompt", "duration"}
    assert next(c for c in schema["controls"] if c["role"] == "duration")["label"] == "Duration (seconds) (4 to 30)"
    assert schema["seconds"] == {"min": 4, "max": 30}   # the model's lengths, as its provider says
    assert [o["id"] for o in schema["options"]] == ["resolution", "aspect_ratio", "sound"]
    assert schema["slots"] == {"first_frame": "4:image", "last_frame": "5:image"}
    assert workflows.describe(load("speech"))["seconds"] == {}   # a model that does not say


def test_the_choices_and_values_reach_the_models_input():
    wf, _ = seedance()
    graph, ctx = workflows.build_prompt(wf, {"values": {PROMPT: "She waves.", DURATION: 10},
                                             "options": {"resolution": "1080p", "sound": "on"}})
    assert provider_input(wf, graph) == {"prompt": "She waves.", "duration": 10, "resolution": "1080p",
                                         "aspect_ratio": "16:9", "sound": True}
    assert ctx["duration"] == 10.0 and ctx["resolution"] == "1080p" and ctx["sound"] == "on"
    with pytest.raises(workflows.WorkflowError, match="not a choice for Resolution"):
        workflows.build_prompt(wf, {"values": {PROMPT: "x"}, "options": {"resolution": "8k"}})


def test_a_required_file_must_be_given_and_an_optional_one_is_left_out():
    with pytest.raises(workflows.WorkflowError, match="Add a file"):
        workflows.build_prompt(load("upscale_video"), {"values": {}, "refs": {}})
    graph, _ = workflows.build_prompt(load("upscale_video"), {"values": {}, "refs": {"2:video": {"comfy_name": "scene_a.mp4"}}})
    assert provider_input(load("upscale_video"), graph)["video"] == {"file": "scene_a.mp4", "kind": "video"}
    wf, _ = seedance()
    graph, _ = workflows.build_prompt(wf, {"values": {PROMPT: "x"}})
    assert not {"first_frame", "last_frame", "reference_video", "reference_images"} & set(provider_input(wf, graph))


def test_a_long_video_is_offered_in_clips_and_its_count_is_in_the_summary():
    _, schema = seedance()
    assert schema["chain"]   # a prompt, a length and a first frame: a long video is made clip by clip
    ctx = workflows.context(schema, {"values": {DURATION: 10}, "clips": 3})
    assert ctx["clips"] == 3 and workflows.summary(schema, ctx).endswith("3 × 10 s")
    assert workflows.clip_count(schema, {"clips": 3}) == 3
    assert "clips" not in workflows.context(schema, {})
    assert not workflows.describe(load("nano_banana_pro"))["chain"]   # a picture is never chained


def test_estimates_come_from_history():
    wf, schema = seedance()
    settings = {"values": {PROMPT: "x", DURATION: 10}, "options": {"resolution": "720p"}}
    assert workflows.estimate(wf, settings)["minutes"] is None
    ctx = workflows.context(schema, settings)
    history = [{"workflow": wf["id"], "context": dict(ctx, seed=1), "seconds": 600}]
    found = workflows.estimate(wf, settings, history)
    assert found["minutes"] == 10.0 and found["measured"]


def test_video_sizes_are_on_the_grid():
    sizes = {480: (864, 480), 720: (1280, 736), 768: (1344, 768), 1080: (1920, 1088)}
    for resolution, (long_edge, short_edge) in sizes.items():
        assert workflows.video_size(resolution, "landscape") == (long_edge, short_edge)
        assert workflows.video_size(resolution, "portrait") == (short_edge, long_edge)
        assert workflows.video_size(resolution, "square") == (short_edge, short_edge)
        assert long_edge % 32 == 0 and short_edge % 32 == 0
    assert workflows.video_size(720, "portrait", 64) == (704, 1280)   # a coarser grid rounds down


def test_media_join_and_last_frame(tmp_path):
    """Two generated test clips are joined; the shared frame between them is dropped."""
    from scene import media

    async def go():
        clips = []
        for i, colour in enumerate(("red", "blue")):
            clip = tmp_path / "clip{}.mp4".format(i)
            await media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color={}:s=64x64:r=24:d=1".format(colour),
                                "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest", "-pix_fmt", "yuv420p", clip)
            clips.append(clip)
        frame = await media.last_frame(clips[0], tmp_path / "last.png")
        joined = await media.join(clips, tmp_path / "joined.mp4")
        piece = await media.cut_audio(clips[0], 0.25, 0.5, tmp_path / "piece.wav")
        return frame, await media.probe(joined), await media.probe(piece)

    frame, joined, piece = asyncio.run(go())
    assert frame.stat().st_size > 0
    assert joined["audio"] and 1.9 < joined["seconds"] < 2.05   # 2 s minus the one shared frame
    assert 0.45 < piece["seconds"] < 0.55


def test_a_workflow_of_a_fixed_length_is_billed_for_it():
    from scene.api import studio
    wf = {"id": "video/fixed_15s", "profile": {"pricing": {"fixed_seconds": 15}}}
    schema = {"options": [], "controls": [], "size": None}
    assert asyncio.run(studio.billed_seconds(None, wf, schema, {})) == 15.0

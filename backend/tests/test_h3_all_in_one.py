"""H3 All In One, the MiniMax H3 default, as its API export and the change notes of 9 November describe it: what a job
sends when no choice is made, Best upscale offered only when Upscale video or Sharpen first frame is on, the four
switches refused before queueing without what they work on (each fails the job on ComfyUI otherwise), and the time
estimates from the measured runs. Read from the files alone, with no ComfyUI."""

import json
from pathlib import Path

import pytest

from scene.comfy import workflows

ROOT = Path(__file__).resolve().parents[2]
ID = "video/h3_all_in_one"
NODES = json.loads((Path(__file__).parent / "fixtures" / "node_definitions.json").read_text(encoding="utf-8"))


def _wf():
    return workflows.load_workflow(ROOT / "workflows" / (ID + ".json"), NODES, ID)


def _build(options=None, refs=(), values=None):
    settings = {"values": {"100:value": "The main character waves.", **(values or {})}, "options": options or {},
                "name": "job", "clips": 1, "refs": {r: {"comfy_name": "scene_{}.png".format(r.split(":")[0])} for r in refs}}
    return workflows.build_prompt(_wf(), settings)


def test_a_job_with_no_choice_made_sends_the_defaults():
    graph, ctx = _build()
    value = lambda nid: graph[nid]["inputs"]["value"]
    assert (value("500"), value("501"), value("502"), value("102")) == (3, 720, False, 5.0)   # high, 720, 16:9, 5 s
    assert value("506") is True and value("107") is True and value("109") is False          # sound, reference mode
    assert value("409") is False and value("462") == 1080 and value("527") is True and value("523") is False
    assert not any(value(n) for n in ("403", "404", "407", "408"))
    assert {o: ctx[o] for o in ("engine", "quality", "sound", "keyframes", "upscale", "sharpen", "best_upscale", "smooth")} == {
        "engine": "reference", "quality": "high", "sound": "on", "keyframes": "off", "upscale": "off", "sharpen": "off",
        "best_upscale": "7b", "smooth": "off"}
    # a new random seed in every seed of the graph; the file name saved in CHARACTER 1 is not sent
    assert value("106") == ctx["seed"] == graph["452"]["inputs"]["seed"] == graph["463"]["inputs"]["seed"]
    assert graph["201"]["inputs"]["image"] == "none"
    assert graph["16"]["inputs"]["filename_prefix"] == "video/job"


def test_the_upscale_goes_to_1080_only():
    schema = workflows.describe(_wf())
    assert "462:value" not in {c["id"] for c in schema["controls"]}   # no field for it
    graph, _ = _build({"upscale": "on"}, values={"462:value": 1440})
    assert graph["409"]["inputs"]["value"] is True and graph["462"]["inputs"]["value"] == 1080


@pytest.mark.parametrize("upscale, sharpen, offered", [("off", "off", False), ("on", "off", True), ("off", "on", True), ("on", "on", True)])
def test_best_upscale_is_offered_only_when_upscale_video_or_sharpen_first_frame_is_on(upscale, sharpen, offered):
    best = next(o for o in workflows.describe(_wf())["options"] if o["id"] == "best_upscale")
    assert workflows.shown(best, {"upscale": upscale, "sharpen": sharpen}) is offered
    # Not offered, it stays on its default (7B) whatever was sent.
    graph, ctx = _build({"upscale": upscale, "sharpen": sharpen, "best_upscale": "3b"}, ["209:image"])
    assert ctx["best_upscale"] == ("3b" if offered else "7b")
    assert graph["527"]["inputs"]["value"] is (not offered)


def test_smooth_motion_switches_rife_on():
    graph, ctx = _build({"smooth": "on"})
    assert graph["523"]["inputs"]["value"] is True and ctx["smooth"] == "on"


@pytest.mark.parametrize("options, refs, refused, enough", [
    ({"sharpen": "on"}, [], "Sharpen first frame needs a first frame", ["209:image"]),
    ({"sharpen": "on", "keyframes": "opening"}, ["401:image"], None, None),   # the built opening frame is a first frame
    ({"sound": "own_voice"}, [], "Keep my voice track needs a VOICE TRACK", ["211:audio"]),
    ({"keyframes": "opening"}, [], "Building the opening frame needs", ["401:image"]),
    ({"keyframes": "both"}, [], "Building the opening frame needs", ["401:image"]),
])
def test_a_switch_without_what_it_works_on_is_refused(options, refs, refused, enough):
    if refused:
        with pytest.raises(workflows.WorkflowError, match=refused):
            _build(options, refs)
    _build(options, refs + (enough or []))   # with it, the job builds


def test_building_the_end_frame_needs_the_opening_frame_built():
    profile = _wf()["profile"]
    nodes = {"403": {"inputs": {"value": False}}, "404": {"inputs": {"value": True}}}
    with pytest.raises(workflows.WorkflowError, match="end frame needs the opening frame"):
        workflows.check(profile, nodes, set())
    nodes["403"]["inputs"]["value"] = True
    workflows.check(profile, nodes, {"401:image"})
    graph, _ = _build({"keyframes": "both"}, ["401:image"])   # the form sets the two together
    assert graph["403"]["inputs"]["value"] is True and graph["404"]["inputs"]["value"] is True


def test_resolution_1080_asks_first_and_offers_720_with_the_upscale():
    warning = workflows.describe(_wf())["confirm"][0]
    assert warning["when"] == {"resolution": 1080} and "Resolution 720" in warning["message"]
    assert warning["alt"]["set"] == {"resolution": 720, "upscale": "on"}


def test_the_estimate_comes_from_the_measured_runs():
    wf = _wf()

    def text(seconds=5, resolution=720, **options):
        return workflows.estimate(wf, {"values": {"102:value": seconds, "501:value": resolution}, "options": options})["text"]

    assert text() == "about 8.0 min"                                   # high, 720, 5 s
    assert text(10, quality="medium") == "about 14 min"
    assert text(3, 480, quality="low") == "about 1.0 min"
    assert text(upscale="on") == "~11 min (est.)"                      # 8 + 2:33 with 7B, never timed as one run
    assert text(upscale="on", best_upscale="3b") == "~10 min (est.)"   # 8 + 2:16 with 3B
    assert text(resolution=1080) == "no estimate yet (it appears after the first run)"


def test_an_earlier_run_is_matched_whatever_was_read_from_its_file():
    wf = _wf()
    settings = {"values": {"102:value": 5, "501:value": 720}, "options": {}}
    ctx = workflows.context(workflows.describe(wf), settings)
    run = {"workflow": ID, "seconds": 300, "context": dict(ctx, seed=7, width=1280, height=720, fps=24.0)}
    assert workflows.estimate(wf, settings, [run])["text"] == "about 5.0 min, from your earlier runs"

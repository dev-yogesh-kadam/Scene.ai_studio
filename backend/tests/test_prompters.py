"""Prompt guides: every workflow that takes a prompt has its model's guide, and the agent is given each guide once."""

import json

import studio_models
from scene import agent, prompters
from scene.providers.workflows import workflow_id


def test_every_picture_and_video_model_with_a_prompt_has_a_guide():
    guides = prompters.load()
    assert len({g["id"] for g in guides}) == len(guides)   # one file per model family
    for model in studio_models.MODELS:
        if model["capability"] not in ("text_to_video", "image"):
            continue   # sound, the upscalers and lip sync, which take no written shot
        assert prompters.for_workflow(workflow_id(model["capability"], model["id"]), guides), model["id"]


def test_a_guide_is_found_by_workflow_id():
    assert prompters.for_workflow("video/@minimax_h3")["id"] == "minimax-h3"
    assert prompters.for_workflow("video/@minimax_h3_max")["id"] == "minimax-h3"
    for seedance in ("seedance_2_5", "seedance_2_0", "seedance_2_0_fast", "seedance_2_0_mini", "seedance_2_5_flash"):
        assert prompters.for_workflow("video/@" + seedance)["id"] == "seedance"     # the craft prompters' block layout
    assert prompters.for_workflow("video/@wan_3_0")["id"] == "wan-3" and prompters.for_workflow("video/@wan_3_0_prime")["id"] == "wan-3"
    assert prompters.for_workflow("video/@kling_4.0")["id"] == "generation"
    assert prompters.for_workflow("image/@nano-banana-pro")["id"] == "generation"
    assert prompters.for_workflow("audio/@music") is None
    assert prompters.for_workflow("video/h3_chunk") is None   # a ComfyUI workflow of before: its guide is archived


def test_each_guide_goes_once_with_the_workflows_it_is_for(tmp_path):
    (tmp_path / "a.md").write_text("id: a\ntitle: A\nworkflows: ^video/a\nlength: 10 words\n---\nWrite it so.\n", encoding="utf-8")
    (tmp_path / "bad.md").write_text("id: bad\nworkflows: (\n---\nbroken\n", encoding="utf-8")
    text = prompters.part(["video/a1", "video/a2", "image/b"], folder=tmp_path)
    assert text.count("Write it so.") == 1 and "video/a1, video/a2" in text and "10 words" in text
    assert prompters.part(["image/b"], folder=tmp_path) == ""


def test_a_prompt_longer_than_its_model_reads_goes_back_to_be_shortened():
    h3 = {"id": "video/@minimax_h3"}
    limit = prompters.for_workflow(h3["id"])["limit"]
    assert agent.too_long(h3, "word " * limit, "word " * limit) is None
    said = agent.too_long(h3, "word " * (limit + 1), "")
    assert "{} words".format(limit + 1) in said and "MiniMax" in said
    # what the studio adds (camera words, the cast in words) must still fit what a job takes
    assert "characters" in agent.too_long({"id": "video/unknown"}, "short", "x" * (agent.PROMPT_CHARS + 1))
    assert all(g["limit"] > 0 for g in prompters.load())


def test_a_craft_prompters_long_block_prompt_fits_its_models_own_limit():
    seedance = {"id": "video/@seedance_2_5", "prompt_chars": 10000}
    blocks = "GOAL\nMaya crosses the harbour.\n\nASSETS\n" + "Maya maps to @Image1; use only facial features. " * 100   # ~800 words, ~4,800 characters
    assert len(blocks) > agent.PROMPT_CHARS and agent.too_long(seedance, blocks, blocks) is None
    assert agent.prompt_chars(seedance) == 10000 and agent.prompt_chars({"id": "video/x"}) == agent.PROMPT_CHARS
    assert "characters" in agent.too_long(seedance, "short", "x" * 10001)
    assert "words" in agent.too_long(seedance, "word " * 1401, "")


def test_the_agent_is_told_when_to_pick_a_workflow():
    schema = {"id": "image/x", "title": "X", "description": "", "pick_when": "A hero picture.",
              "controls": [{"id": "1:text", "role": "prompt", "type": "text", "default": ""}], "refs": [], "options": []}
    assert agent.offer(schema)["pick_when"] == "A hero picture."
    assert "pick_when" not in agent.offer(dict(schema, pick_when=""))


def test_the_agent_is_told_the_guide_and_given_its_text():
    schema = {"id": "video/@minimax_h3", "title": "MiniMax H3", "description": "", "controls": [{"id": "1:text", "role": "prompt", "type": "text", "default": ""}],
              "refs": [], "options": [], "hints": ["x" * 500]}
    offer = agent.offer(schema)
    assert offer["prompt_guide"] == "minimax-h3" and len(offer["prompt_tips"][0]) == agent.TIP_CHARS
    parts = dict(agent.question_parts("a dog runs", [offer], [], "video/@minimax_h3"))
    assert "SHOTS" in parts["prompting"] and json.loads(parts["workflows"].split("\n", 1)[1])["prompt_guide"] == "minimax-h3"
    assert "prompting" not in dict(agent.question_parts("a dog", [{"id": "w"}], [], "w"))

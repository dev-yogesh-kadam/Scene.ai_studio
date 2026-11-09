"""Prompt guides: every workflow that takes a prompt has its model's guide, and the agent is given each guide once."""

import json
from pathlib import Path

from scene import agent, prompters

WORKFLOWS = Path(__file__).resolve().parents[2] / "workflows"


def test_every_picture_and_video_workflow_with_a_prompt_has_a_guide():
    guides = prompters.load()
    assert len({g["id"] for g in guides}) == len(guides)   # one file per model family
    for path in sorted(WORKFLOWS.glob("*/*.studio.json")):
        kind, name = path.parent.name, path.name[:-len(".studio.json")]
        if kind not in ("image", "video") or name.startswith("video_lipsync"):
            continue   # sound, the upscaler, and lip sync, which takes a voice and a face and no written shot
        assert prompters.for_workflow("{}/{}".format(kind, name), guides), name


def test_a_guide_is_found_by_workflow_id():
    assert prompters.for_workflow("video/h3_chunk")["id"] == "minimax-h3"
    assert prompters.for_workflow("video/talking_head_narration")["id"] == "talking-head"   # the voice file carries the words
    assert "Never the spoken words" in prompters.for_workflow("video/talking_head_narration")["text"]
    assert prompters.for_workflow("video/video_v2v_ltx23_iclora")["id"] == "ltx"
    assert prompters.for_workflow("video/video_v2v_wan_vace")["id"] == "wan"
    assert prompters.for_workflow("image/image_t2i_flux2_klein_9b")["id"] == "flux2"
    assert prompters.for_workflow("image/image_t2i_flux3_klein")["id"] == "flux3-klein"
    assert prompters.for_workflow("audio/audio_minimax_music_3") is None


def test_each_guide_goes_once_with_the_workflows_it_is_for(tmp_path):
    (tmp_path / "a.md").write_text("id: a\ntitle: A\nworkflows: ^video/a\nlength: 10 words\n---\nWrite it so.\n", encoding="utf-8")
    (tmp_path / "bad.md").write_text("id: bad\nworkflows: (\n---\nbroken\n", encoding="utf-8")
    text = prompters.part(["video/a1", "video/a2", "image/b"], folder=tmp_path)
    assert text.count("Write it so.") == 1 and "video/a1, video/a2" in text and "10 words" in text
    assert prompters.part(["image/b"], folder=tmp_path) == ""


def test_a_prompt_longer_than_its_model_reads_goes_back_to_be_shortened():
    wan = {"id": "video/video_v2v_wan_vace"}
    limit = prompters.for_workflow(wan["id"])["limit"]
    assert agent.too_long(wan, "word " * limit, "word " * limit) is None
    said = agent.too_long(wan, "word " * (limit + 1), "")
    assert "{} words".format(limit + 1) in said and "Wan" in said
    # what the studio adds (camera words, the cast in words) must still fit what a job takes
    assert "characters" in agent.too_long({"id": "video/unknown"}, "short", "x" * (agent.PROMPT_CHARS + 1))
    assert all(g["limit"] > 0 for g in prompters.load())


def test_the_agent_is_told_when_to_pick_a_workflow():
    schema = {"id": "image/x", "title": "X", "description": "", "pick_when": "A hero picture.",
              "controls": [{"id": "1:text", "role": "prompt", "type": "text", "default": ""}], "refs": [], "options": []}
    assert agent.offer(schema)["pick_when"] == "A hero picture."
    assert "pick_when" not in agent.offer(dict(schema, pick_when=""))


def test_the_agent_is_told_the_guide_and_given_its_text():
    schema = {"id": "video/h3_chunk", "title": "H3 Chunk", "description": "", "controls": [{"id": "1:text", "role": "prompt", "type": "text", "default": ""}],
              "refs": [], "options": [], "hints": ["x" * 500]}
    offer = agent.offer(schema)
    assert offer["prompt_guide"] == "minimax-h3" and len(offer["prompt_tips"][0]) == agent.TIP_CHARS
    parts = dict(agent.question_parts("a dog runs", [offer], [], "video/h3_chunk"))
    assert "SHOTS" in parts["prompting"] and json.loads(parts["workflows"].split("\n", 1)[1])["prompt_guide"] == "minimax-h3"
    assert "prompting" not in dict(agent.question_parts("a dog", [{"id": "w"}], [], "w"))

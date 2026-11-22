"""The agent's craft tools in the Frameo manner: the preset library, skills loaded from the catalogue, what a shot's
review checks closely, and the close study of a picture (look "deep")."""

import json

from scene import presets, skills
from test_agent_conversation import STEP, item
from test_agent_shots import hosted
from test_api import register


def test_presets_are_found_by_words_and_category_and_say_what_they_clash_with():
    found = presets.search("golden")
    assert found[0]["id"] == "golden-hour" and "overcast" in found[0]["clashes"]
    assert all(p["category"] == "camera-settings" for p in presets.search("", "camera-settings"))
    assert "No preset fits" in presets.for_tool("zzzz")
    assert presets.for_tool("push", "lighting-and-mood").startswith('{"id": "push-in"')   # not in that category: the whole library
    assert len({p[0] for p in presets.PRESETS}) == len(presets.PRESETS)   # every id once


def test_the_agent_looks_up_presets_and_loads_a_skill_from_the_catalogue(client, monkeypatch):
    register(client)
    seen = hosted(monkeypatch, client, {"tool": "preset_search", "query": "push in"},
                  {"tool": "read_skill", "op": "camera-coverage", "query": "0"},
                  {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "hello there, with camera-coverage"})   # the user names the skill
    told = [m["content"] for m in seen[-1] if m["role"] == "user"]
    asked = "\n".join(m["content"] for m in seen[0])
    assert "camera-coverage (craft" in asked and "Presets:" in asked   # the catalogue (craft skills marked) and the rules went with it
    assert any('"id": "push-in"' in t for t in told)
    assert any("Study the subject first" in t for t in told)            # the whole skill, loaded


def test_a_steps_check_goes_with_it_and_its_review_reads_it(client, monkeypatch):
    register(client)
    hosted(monkeypatch, client, {"tool": "finish", "reply": "One shot.", "steps": [dict(STEP, check="the dog keeps its red collar")]})
    plan = client.post("/api/agent/plan", json={"instruction": "a dog"}).json()
    assert plan["steps"][0]["settings"]["check"] == "the dog keeps its red collar"


def test_a_deep_look_studies_a_picture_and_keeps_its_facts(client, monkeypatch, tmp_path):
    me = register(client)
    folder = client.app.state.outputs.folder(me["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "cafe.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    shot = item(client, me["id"], "Cafe", filename="cafe.png")
    studied = {"subject": "a small cafe", "expressions": "", "clothing_pose": "", "background": "shelves", "composition": "centred",
               "aspect": "landscape", "lighting": "warm window light from the left", "scene": "interior cafe, morning", "room": "wooden tables",
               "atmosphere": "calm", "props": "a brass bell", "motion": "still", "story": "opening time",
               "text": [{"words": "OPEN", "where": "on the door"}], "preserve": ["the brass bell"], "avoid": ["people"],
               "photoreal": True, "has_person": False}

    async def fake_analyse(picture, name="", kind="image", model=None):
        return studied
    monkeypatch.setattr(client.app.state.agent, "analyse", fake_analyse)

    async def fake_picture(path):
        return "x"
    from scene import memory
    monkeypatch.setattr(memory, "_picture", fake_picture)
    seen = hosted(monkeypatch, client, {"tool": "look", "item": shot, "op": "deep"}, {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "study the cafe"})
    assert any('"words": "OPEN"' in m["content"] for m in seen[-1] if m["role"] == "user")
    facts = json.loads(client.app.state.db.one("SELECT facts FROM generations WHERE id = ?", (shot,))["facts"])
    assert facts["preserve"] == ["the brass bell"] and facts["has_person"] is False


def test_craft_skills_are_never_picked_by_their_words_alone():
    # a craft skill is loaded by a skill that calls for it, or named with /<id>; its words alone do not pick it. The
    # director is the one that comes on its own, and only for multi-shot story work (skills.wants_directing)
    assert "camera-coverage" not in [s["id"] for s in skills.pick("give me different angles of this cafe")]
    assert [s.get("auto") for s in skills.pick("direct this script for me") if s["id"] == "shot-planner"] == [True]
    assert "sound-pass" not in [s["id"] for s in skills.pick("add background music to it")]


def test_the_director_comes_on_its_own_for_multi_shot_story_work_only():
    def directs(said, history=()):
        return "shot-planner" in [s["id"] for s in skills.pick(said, history)]
    for said in ("a short film: two brothers fix their father's boat", "plan the shots of this scene: she enters, argues and leaves",
                 "a music video for my song about the monsoon", "turn this story into scenes", "write me a three minute drama"):
        assert directs(said), said
    for said in ("a single shot of a cat on a windowsill", "make a 5 second video of a dog running", "trim this film to 10 seconds",
                 "a kinetic typography video of our story", "make a logo reveal for our brand film", "a picture of a dragon",
                 "I always make short films for clients", "hello, what can you do?", "split the movie in three"):
        assert not directs(said), said
    # a short follow-up is read with the message before it
    assert directs("yes, portrait", [{"instruction": "a short film about a lighthouse keeper", "reply": "Which shape?"}])
    # a user who names the director gets it as theirs, not as the studio's own; a long skill named is the whole procedure
    assert [s.get("auto") for s in skills.pick("a short film about rain", force=["shot-planner"])] == [None]
    assert [s["id"] for s in skills.pick("angles please", force=["camera-coverage"])][0] == "camera-coverage"
    assert all(s["craft"] for s in skills.load() if s["id"] in ("shot-planner", "camera-coverage", "callback-frames", "sound-pass"))

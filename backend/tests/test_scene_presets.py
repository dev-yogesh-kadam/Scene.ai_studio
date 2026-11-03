"""The scene presets in the preset library (presets.py): one per kind of scene, found by name and read whole."""

from scene import presets

KINDS = {"chase", "comedy", "confrontation", "conversation", "fight", "grief", "horror", "introduction", "montage",
         "performance", "reveal", "romance", "suspense", "triumph"}


def test_all_fourteen_are_loaded_with_their_use_and_what_they_mix_with():
    assert set(presets.SCENES) == KINDS
    assert presets.SCENE_CATEGORY in presets.CATEGORIES
    fight = presets.SCENES["fight"]
    assert fight["title"] == "Fight"
    assert fight["when"].startswith("Use for any physical clash")
    assert fight["mixes"] == ["confrontation", "chase", "horror"]
    for scene in presets.SCENES.values():
        for heading in ("## What the scene is really about", "## Pick the engine", "## The turn", "## Traps"):
            assert heading in scene["craft"], (scene["id"], heading)


def test_a_name_alone_gives_the_whole_craft_one_preset_at_a_time():
    text = presets.for_tool("fight")
    assert text.startswith("Scene preset fight (Fight).")
    assert "## For the video model" in text
    both = presets.for_tool("chase and suspense scene")
    assert both.startswith("Scene preset chase") and "Also named: suspense." in both
    assert "## Staging and blocking" in both and both.count("## Traps") == 1
    assert len(max((presets.for_tool(k) for k in KINDS), key=len)) < 8000   # fits the agent's tool result


def test_other_searches_find_scenes_by_name_or_use_but_never_by_their_craft():
    close = presets.search("close-up")   # framing, not the scene craft that says close-up
    assert close and all(p["category"] != "scene-types" for p in close)
    assert presets.for_tool("close-up reveal").startswith("{")   # a name among other words is a search, not the craft
    mixed = presets.search("reveal")
    assert any(p["id"] == "reveal" and p["category"] == "scene-types" and "craft" not in p for p in mixed)
    assert all(p["category"] == "scene-types" for p in presets.search("", "scene-types"))
    assert len(presets.search("", "scene-types")) == presets.MOST_FOUND
    assert not any(p["category"] == "scene-types" for p in presets.search("", "framing"))
    assert presets.for_tool("pursuit", "scene-types").startswith('{"id": "chase"')
    assert "fight" in presets.RULES and "scene-types" in presets.RULES

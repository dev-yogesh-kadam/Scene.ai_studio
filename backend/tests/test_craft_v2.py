"""Craft skills v2 in the studio (4 November 2026): the ported skills keep every v2 word (only the models the studio
does not have are swapped), the script writer's scene recipes are presets read whole, a craft skill's name for another
finds it here, a long skill is read in parts that each fit in one tool result, a story is kept in NeuralCore as a
script, a table's asset handles are shown as their entries, and a long run's reply keeps a story whole."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from scene import agent, presets, skills
from test_agent_features_nov import told
from test_agent_memory import film
from test_agent_shots import hosted
from test_api import register

V2 = Path(__file__).resolve().parents[2] / "content" / "craft-skills" / "v2" / "craft skills"
SEEDANCE_AND_WAN_ROWS = {"`": 6, "|": 12, "seedance_2_5": 2, "seedream-5-0-pro": 1, "craft-prompter-seedance-2-5": 1, "Board": 2,
                         "Chain": 1, "Recall": 2, "seedance_2_0": 1, "seedance_2_0_fast": 1, "seedance_2_0_mini": 1,
                         "craft-prompter-seedance-2": 1, "wan_3_0": 1, "wan_3_0_prime": 1, "craft-prompter-wan-3": 1}
PORTED = {   # studio skill: (its v2 file, the v2 words it may leave out: the models the studio does not have)
    "script-to-video": ("Header skills/script-to-video.md", SEEDANCE_AND_WAN_ROWS),
    "script-writer": ("script writer/craft-script-writer.md", {}),
    "asset-designer": ("asset creation/craft-asset-designer.md", {"seedream-5-0-pro": 1}),
    "director": ("director/craft-director.md", {}),
    "anchor": ("continuity/craft-anchor.md", {"model_name": 1, "seedream-5-0-pro": 1}),
    "continuity-chain": ("continuity/craft-continuity-chain.md", {}),
    "continuity-board": ("continuity/craft-continuity-board.md", {}),
    "continuity-recall": ("continuity/craft-continuity-recall.md", {}),
    "prompter-minimax-h3": ("prompters/craft-prompter-minimax-h3.md", {}),
}


def words(text):
    return Counter(re.findall(r"[\w'’-]+|[^\w\s]", text))


@pytest.mark.skipif(not V2.is_dir(), reason="the craft skills v2 folder is not here")
@pytest.mark.parametrize("sid", list(PORTED))
def test_a_ported_skill_keeps_every_v2_word_but_the_models_the_studio_lacks(sid):
    source, may_go = PORTED[sid]
    raw = (V2 / source).read_text(encoding="utf-8").replace("\r\n", "\n")
    v2_body = raw[raw.index("\n---\n", 4) + 5:]
    ours = skills.find(sid)
    gone = words(v2_body) - words(ours["text"])
    assert all(gone[w] <= may_go.get(w, 0) for w in gone), (sid, {w: n for w, n in gone.items() if n > may_go.get(w, 0)})
    assert ours["craft"] == (sid != "script-to-video") and ours["title"].startswith(("Craft ", "Script to Video"))


def test_the_studio_adds_its_own_lines_to_the_header_and_keeps_its_steps():
    header = skills.find("script-to-video")["text"]
    assert "## 0 — Is this a film? (Studio)" in header and "## 9 — The cut (Studio)" in header      # D3, D2
    assert "a fifth kind, Audio" in header and "480p and 768p (Default)" in header                  # D1, D8
    assert "on H3 Chunk that is Board (Default) and Recall" in header                               # D4
    assert "use `minimax_h3` and FLUX.2 dev." in header and "seedance" not in header.split("Chain is left out")[0]
    assert skills.find("anchor")["text"].count("FLUX.2 dev") >= 2                                   # D7
    assert "Studio: on its own" in skills.find("director")["text"]                                  # D5
    assert not skills.find("script-to-video")["next"]   # the craft skills it loads are craft: no hand-off line after it
    guide = Path(skills.__file__).with_name("prompters") / "minimax-h3.md"
    assert "they count as asked for" in guide.read_text(encoding="utf-8")                          # D10


def test_the_script_writers_scene_recipes_are_read_whole_by_their_names():
    assert len(presets.RECIPES) == 23 and {"scene-awakening", "scene-status", "scene-trial"} <= set(presets.RECIPES)
    whole = presets.for_tool("scene-chase", "scene-recipes")
    assert whole.startswith("Scene recipe scene-chase (Chase).") and "## Pick the engine" in whole and "## Traps" in whole
    assert "Camera and cutting" not in whole                                          # the writing recipe, no camera
    assert presets.for_tool("chase", "scene-recipes").startswith("Scene recipe scene-chase")   # in its own category the kind is enough
    assert presets.for_tool("chase").startswith("Scene preset chase") and "Camera and cutting" in presets.for_tool("chase")   # v1 stays
    assert "Also named: scene-grief" in presets.for_tool("scene-fight scene-grief")
    assert "tension-slow" in presets.for_tool("tension", "scene-recipes")            # the category's short tips are still found
    assert "scene-recipes" in presets.CATEGORIES and "scene-humiliation" in presets.RULES
    assert presets.RECIPES["scene-awakening"]["mixes"][:2] == ["scene-humiliation", "scene-trial"]


def test_a_craft_skills_name_for_another_finds_it_here():
    assert skills.find("craft-director")["id"] == "director" and skills.find("craft-prompter-minimax-h3")["id"] == "prompter-minimax-h3"
    assert [s["id"] for s in skills.pick("x", force=["craft-anchor", "anchor"])] == ["anchor"]
    assert skills.canonical("Craft-Script-Writer") == "script-writer" and skills.find("craft-nothing") is None


def ready(monkeypatch, brain):
    async def checked(*args, **kwargs):
        return {"ready": True, "missing": [], "unsupported": [], "adaptation": "", "message": ""}
    monkeypatch.setattr(brain, "preflight", checked)


def test_a_craft_skill_comes_whole_in_one_read_and_is_not_sent_twice(client, monkeypatch):
    register(client)
    ready(monkeypatch, client.app.state.agent)
    seen = hosted(monkeypatch, client, {"tool": "read_skill", "op": "craft-director", "query": "0"},
                  {"tool": "read_skill", "op": "director", "query": "4"},
                  {"tool": "read_skill", "op": "script-to-video", "query": "3"},
                  {"tool": "finish", "reply": "ok"})
    plan = client.post("/api/agent/plan", json={"instruction": "/script-to-video a story about a lighthouse", "run": "s2v-2"}).json()
    whole, again, given = [t.split(":\n", 1)[1] for t in told(seen) if t.startswith("Result of read_skill")]
    director = skills.find("director")["text"]
    assert len(director) > agent.TOOL_RESULT and len(whole) <= agent.SKILL_RESULT    # more than any other tool's result, in one
    assert whole.startswith("Craft Director (skill director") and director in whole and "Parts:" not in whole
    assert "is loaded already" in again and "## 4. Shots" not in again                 # asked again: where it is, not a copy
    assert "is given to you whole" in given and "## " not in given                     # the skill in use is in the prompt
    assert any(e["text"].startswith("“Craft Director” is loaded already") for e in plan["activity"])


def test_a_skill_is_sent_once_to_a_claude_session_and_again_after_a_compaction(client, monkeypatch, tmp_path):
    from scene import claude
    register(client)
    brain = client.app.state.agent
    brain.services["claude"] = {"id": "claude", "name": "Claude", "url": "claude-code", "key": "", "models": ["sonnet"], "only": "",
                                "cli": "claude.exe", "timeout": 60, "fast": "", "home": str(tmp_path), "window": 1_000_000}
    ready(monkeypatch, brain)
    got, asked = [], []

    async def ask_with_tools(system, message, workflow_ids, tools, finishing=None, rounds=0, thread=None, model=None, **kw):
        asked.append(message)
        got.append(await tools["read_skill"]({"op": "craft-director", "query": "0"}))
        if len(got) == 2:
            thread["compacted"] = (thread.get("compacted") or 0) + 1   # Claude Code compacted the session in this turn
        thread.update(id="s-1", size=10_000)
        return {"reply": "Answer {}".format(len(got)), "steps": [], "thought": "", "direction": "", "question": None,
                "tools": [], "tokens": {}, "model": model}

    async def rename(s, thread, title):
        pass
    monkeypatch.setattr(brain, "ask_with_tools", ask_with_tools)
    monkeypatch.setattr(claude, "rename", rename)
    film = client.post("/api/projects", json={"name": "Film"}).json()
    history = []
    for text in ("/script-to-video a story about a lighthouse", "go on", "go on"):
        reply = client.post("/api/agent/plan", json={"instruction": text, "project_id": film["id"], "run": "tab1", "tab": "Agent 1",
                                                     "model": "claude/sonnet", "history": list(history)}).json()["reply"]
        history.append({"instruction": text, "reply": reply})
    director = skills.find("director")["text"]
    assert director in got[0]                                                 # whole, the first time
    assert "is loaded already" in got[1] and director not in got[1]          # the session has it: not sent again
    assert director in got[2]                                                 # compacted since: sent again, whole
    assert "is as it was" in asked[1] and "is as it was" not in asked[2]     # after a compaction every part goes again


def test_a_story_is_kept_in_neuralcore_as_a_script(client, monkeypatch):
    register(client)
    project = film(client)
    story = "Ep 1 - The Lantern\n\nRain fell on the harbour, and Maya held the lantern under her coat."
    seen = hosted(monkeypatch, client,
                  {"tool": "state_write", "path": "/script/story", "value": json.dumps(story)},
                  {"tool": "book_save", "text": "Ep 1 - The Lantern", "op": "script", "value": "$state:/script/story"},
                  {"tool": "book_save", "text": "Notes", "op": "script", "value": "Plain words of a script."},
                  {"tool": "book_save", "text": "Ghost", "op": "script", "value": "$state:/script/nothing"},
                  {"tool": "finish", "reply": "ok"})
    client.post("/api/agent/plan", json={"instruction": "keep the story", "project_id": project})
    results = [t for t in told(seen) if t.startswith("Result of book_save")]
    assert json.loads(results[0].split(":\n", 1)[1])["characters"] == len(story) and "nothing is written" in results[2]
    entries = {e["name"]: e for e in client.get("/api/kit", params={"project": project}).json()["entries"]}
    assert entries["Ep 1 - The Lantern"]["kind"] == "text" and entries["Ep 1 - The Lantern"]["tag"] == "script" and "Notes" in entries
    assert client.get("/api/kit/{}/file".format(entries["Ep 1 - The Lantern"]["id"])).text == story


def test_a_tables_asset_handle_is_shown_as_that_entry():
    chips, said = agent.chips_in("```csv\nName,Description,CDN link\nMaya,Sc 1 harbour,asset_id:7\n```", {}, {7: {"name": "Maya", "kind": "image"}})
    assert chips == {"asset:7": {"name": "Maya", "kind": "image"}} and "Maya,Sc 1 harbour,[[asset:7]]" in said


def test_a_long_run_keeps_a_story_whole_in_its_reply():
    story = "word " * 5000
    assert len(agent.shaped({"reply": story})["reply"]) == agent.REPLY_CHARS
    assert agent.shaped({"reply": story}, agent.RUN_REPLY_CHARS)["reply"] == story.strip()

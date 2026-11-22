"""The models that work on a file the user gives (a lip sync, an upscale, and On this PC's transcription and voice
separation): they load, the agent is offered them and builds their steps. On this PC's tools need .venv-audio, so a
test that wants them says they are ready (on_this_pc)."""

import asyncio
import json
import sys
import time

from scene import agent, runs
from scene.api import studio
from scene.comfy import workflows
from scene.providers import local, registry
from scene.providers.local import LocalTools
from test_agent_shots import hosted
from test_api import register

ON_THIS_PC = ["audio/@transcribe", "audio/@transcribe_video", "audio/@separate_voice"]
NEW = ["video/@lip_sync", "upscaler/@upscale_video"] + ON_THIS_PC


def on_this_pc(client):
    """On this PC's models, as if .venv-audio had transcription and voice separation ready: its Python there (this
    one, so it is offered: local.offered) and its tools found installed."""
    db = client.app.state.db
    client.app.state.settings.local_tools_python = sys.executable
    row = next(p for p in registry.providers(db) if p["kind"] == local.KIND)
    key = registry.keys(db, row["id"])[0]
    ready = {"ready": True, "why": ""}
    local._checked[sys.executable] = (time.time(), {"device": "cpu", "transcribe": ready, "separate_voice": ready})
    registry.save_models(db, row["id"], key["id"], asyncio.run(LocalTools(python=sys.executable).models("")))
    client.app.state.router.forget()
    client.app.state.catalog.providers.read_at = 0.0   # read again on the next look


def schema_of(client, workflow_id):
    return workflows.describe(asyncio.run(client.app.state.catalog.load(workflow_id)))


def test_the_new_workflows_load_and_build(client):
    on_this_pc(client)
    listed = {w["id"]: w for w in asyncio.run(client.app.state.catalog.listing())}
    for wid in NEW:
        assert wid in listed and not listed[wid].get("error"), wid
        schema = schema_of(client, wid)
        settings = {"workflow": wid, "values": {}, "clips": 1, "options": {o["id"]: o["default"] for o in schema["options"]},
                    "refs": {r["id"]: {"comfy_name": "scene_x.png"} for r in schema["refs"] if not r["optional"]}}
        workflows.build_prompt(asyncio.run(client.app.state.catalog.load(wid)), settings)   # raises if anything is wrong
    lipsync = schema_of(client, "video/@lip_sync")
    assert lipsync["slots"]["voice_track"] == "3:audio" and all(not r["optional"] for r in lipsync["refs"])
    assert [o["id"] for o in schema_of(client, "audio/@transcribe")["options"]] == ["language", "speakers"]
    assert [(r["id"], r["optional"]) for r in schema_of(client, "audio/@separate_voice")["refs"]] == [("2:audio", False)]


def test_the_agent_is_offered_the_tools_without_a_prompt_when_given_a_file(client):
    on_this_pc(client)
    transcribe, lipsync = schema_of(client, "audio/@transcribe"), schema_of(client, "video/@lip_sync")
    assert agent.offer(transcribe, attached=False) is None          # nothing to work on
    offered = agent.offer(transcribe, attached=True)
    assert offered["prompt"].startswith("none") and any(s["setting"] == "language" for s in offered["settings"])
    assert agent.offer(lipsync, attached=True)["references"][0]["slot"] == "2:video"
    speech = agent.offer(schema_of(client, "audio/@speech"), attached=False)
    free = {s["setting"]: s for s in speech["settings"]}
    assert free["3:value"]["value"] == "any words"   # the voice id: words of its own


def test_a_step_on_them_takes_switches_and_words(client):
    on_this_pc(client)
    transcribe = schema_of(client, "audio/@transcribe")
    made = agent.settings_for(transcribe, {"name": "Listen", "prompt": "", "choices": [
        {"setting": "language", "value": "hi"}, {"setting": "speakers", "value": "on"}, {"setting": "language", "value": "klingon"}]},
                              [], 0, filled={"2:audio"})[0]
    assert made["options"] == {"language": "hi", "speakers": "on"}   # a value it does not have is ignored
    speech = schema_of(client, "audio/@speech")
    said = agent.settings_for(speech, {"name": "Line", "prompt": "Welcome home.", "choices": [{"setting": "3:value", "value": "maya_warm"}]}, [], 0)[0]
    assert said["values"]["2:value"] == "Welcome home." and said["values"]["3:value"] == "maya_warm"
    # a model that takes whole seconds gets whole seconds
    shot = agent.settings_for(schema_of(client, "video/@seedance_2_5"), {"name": "c3", "prompt": "She turns.", "duration": 6.6}, [], 0)[0]
    assert shot["values"]["3:value"] == 6


def test_an_upscale_is_billed_by_the_video_it_is_given(client):
    on_this_pc(client)
    me = register(client)
    clip = client.app.state.db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
                                   "VALUES (?, 'video/@seedance_2_5', 'video', 'c3', 'c3.mp4', '{}', ?, 1)", (me["id"], json.dumps({"duration": 6.3})))
    wf = asyncio.run(client.app.state.catalog.load("upscaler/@upscale_video"))
    seconds = asyncio.run(studio.billed_seconds(client.app.state, wf, workflows.describe(wf), {"parent": clip, "values": {}}, me["id"]))
    assert seconds == 6.3
    assert studio.by_source(wf) and not studio.by_source(asyncio.run(client.app.state.catalog.load("audio/@transcribe")))


def test_the_agent_names_the_speakers_without_touching_a_time(client, monkeypatch):
    me = register(client)
    db = client.app.state.db
    runs.write_many(db, me["id"], "pm-1", "/motion/transcript/lines", {
        "1": {"start": 0.5, "end": 2.0, "speaker": "SPEAKER_00", "text": "The storm came."},
        "2": {"start": 2.4, "end": 3.1, "speaker": "SPEAKER_00", "text": "Run!"}})
    seen = hosted(monkeypatch, client, {"tool": "transcript", "item": 0, "path": "/motion/transcript/lines", "value": '{"1": "narrator", "2": "Maya", "9": "Nobody"}'},
                  {"tool": "finish", "reply": "ok", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "go", "run": "pm-1"})
    assert any('"named": 2' in m["content"] for m in seen[-1] if m["role"] == "user")
    lines = dict(runs.leaves(db, me["id"], "pm-1", "/motion/transcript/lines"))
    assert lines["2"] == {"start": 2.4, "end": 3.1, "speaker": "Maya", "text": "Run!"} and lines["1"]["speaker"] == "narrator"


def test_a_step_on_a_workflow_without_a_prompt_is_planned_and_shown(client, monkeypatch):
    on_this_pc(client)
    me = register(client)
    sound = client.app.state.db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
                                    "VALUES (?, 'upload/file', 'audio', 'Episode', 'episode.mp3', '{}', '{}', 1)", (me["id"],))
    step = {"tool": "generate", "workflow": "audio/@transcribe", "name": "Listen", "prompt": "",
            "uses": [{"item": sound, "asset": 0, "slot": "2:audio"}], "choices": [{"setting": "language", "value": "en"}]}
    hosted(monkeypatch, client, {"tool": "finish", "reply": "Transcribing.", "steps": [step]})
    plan = client.post("/api/agent/plan", json={"instruction": "@1 transcribe it", "selection": [sound]}).json()
    shown = plan["steps"][0]
    assert shown["name"] == "Listen" and shown["prompt"] == "" and shown["settings"]["options"]["language"] == "en"


def test_a_sound_step_on_a_workflow_that_takes_a_sound_is_that_workflow(client, monkeypatch):
    # a model often calls separating a voice "sound": it is the workflow's step, not a sound put on a video
    on_this_pc(client)
    me = register(client)
    sound = client.app.state.db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
                                    "VALUES (?, 'upload/file', 'audio', 'Episode', 'episode.mp3', '{}', '{}', 1)", (me["id"],))
    step = {"tool": "sound", "workflow": "audio/@separate_voice", "name": "Voice stem", "prompt": "", "audio": sound,
            "uses": [{"item": sound, "asset": 0, "slot": "2:audio"}]}
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Separating.", "steps": [step]})
    plan = client.post("/api/agent/plan", json={"instruction": "@1 separate the voice", "selection": [sound]}).json()
    assert [s["name"] for s in plan["steps"]] == ["Voice stem"] and plan["steps"][0]["settings"]
    assert len(seen) == 1   # it could run as it was: no hint went back
    assert "audio/@separate_voice" in agent.takes_sound([agent.offer(schema_of(client, "audio/@separate_voice"))])
    assert not agent.takes_sound([agent.offer(schema_of(client, "video/@seedance_2_5"), True)])


def test_a_plan_that_cannot_be_put_right_goes_back_at_most_twice(client, monkeypatch):
    register(client)
    bad = {"tool": "sound", "workflow": "video/@seedance_2_5", "name": "Nothing to put together", "prompt": ""}
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Here.", "steps": [bad]})
    plan = client.post("/api/agent/plan", json={"instruction": "put music on it"}).json()
    assert len(seen) == 1 + agent.FIX_ROUNDS and plan["steps"] == []
    told = [m["content"] for m in seen[-1] if m["role"] == "user"]
    assert any("generate" in t and "sound tool only puts" in t for t in told)


def test_a_long_skill_run_is_reminded_once_to_save_its_work(client, monkeypatch):
    me = register(client)
    db = client.app.state.db
    assert not runs.saved_any(db, me["id"], "pm-2")
    runs.keep_skill(db, me["id"], "pm-2", 0, "script-to-video")
    assert not runs.saved_any(db, me["id"], "pm-2")   # what the studio keeps for it is not the agent's work
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Pick the models.", "steps": []})
    ready = {"ready": True, "missing": [], "unsupported": [], "adaptation": "", "message": ""}
    monkeypatch.setattr(client.app.state.agent, "preflight", lambda *a, **k: asyncio.sleep(0, ready))
    plan =client.post("/api/agent/plan", json={"instruction": "go", "run": "pm-2"}).json()
    assert plan["reply"] == "Pick the models." and len(seen) == 2
    assert any(agent.SAVE_FIRST in m["content"] for m in seen[-1] if m["role"] == "user")
    runs.write(db, me["id"], "pm-2", "/motion/models", {"image": "image/@nano_banana_pro"}, "agent")
    assert runs.saved_any(db, me["id"], "pm-2")


def test_the_one_sound_attached_fills_a_slot_the_step_left_out(client):
    on_this_pc(client)
    schema = schema_of(client, "audio/@transcribe")
    one = {7: {"name": "Episode", "kind": "audio"}, 8: {"name": "Maya", "kind": "image"}}
    assert [(u["id"], u["slot"]) for u in agent.uses_for(schema, {"uses": []}, one)] == [(7, "2:audio")]
    two = {**one, 9: {"name": "Voice stem", "kind": "audio"}}
    assert agent.uses_for(schema, {"uses": []}, two) == []   # two sounds: it is not guessed
    assert [u["id"] for u in agent.uses_for(schema, {"uses": [], "audio": 9}, two)] == [9]
    assert [u["id"] for u in agent.uses_for(schema, {"uses": [{"item": 7, "asset": 0, "slot": "2:audio"}], "audio": 9}, two)] == [7]

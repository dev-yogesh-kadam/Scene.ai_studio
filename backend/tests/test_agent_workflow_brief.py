"""The workflows a message is given: in full only those of the kinds it is about, every other one in a line, and any of
them in full on demand (workflow_info). The list was about 28,000 characters of every first message, whatever it asked."""

import asyncio
import json

from scene import agent, prompters
from scene.api import workspace
from test_api import register


def _offer(wid, guide=None, **more):
    return {"id": wid, "title": wid.split("/")[1].title(), "makes": wid.split("/")[0], "about": "Makes things. " * 20,
            "settings": [{"setting": "quality", "choices": ["low", "high"]}] * 5, **({"prompt_guide": guide} if guide else {}), **more}


OFFERS = [_offer("video/h3_all_in_one", "minimax-h3", pick_when="Long shots with a cast."), _offer("image/flux"),
          _offer("image/krea", pick_when="Fast drafts."), _offer("audio/song")]


def _workflows(parts):
    return dict(parts)["workflows"].splitlines()[1:]


def test_the_kinds_a_message_is_about():
    assert agent.likely_kinds(["Make a picture of a red kite"]) == {"image"}
    assert agent.likely_kinds(["Make a 6 second clip of it"]) == {"video"}
    assert agent.likely_kinds(["Write a song about kites"]) == {"audio"}
    assert agent.likely_kinds(["A poster and a short video ad with music"]) == {"image", "video", "audio"}
    assert agent.likely_kinds(["go ahead"]) == set(agent.WORKFLOW_KINDS)            # nothing said: every kind, in full
    assert agent.likely_kinds(["un vídeo de una cometa"]) == set(agent.WORKFLOW_KINDS)  # another language: the same
    assert agent.likely_kinds(["make it brighter", "Make a picture of a kite"]) == {"image"}   # the turn before counts


def test_every_workflow_is_listed_and_only_the_kinds_asked_for_in_full():
    parts = agent.question_parts("Make a picture of a red kite", OFFERS, [], "video/h3_all_in_one", detailed={"image"})
    lines = [json.loads(line) for line in _workflows(parts)]
    assert [line["id"] for line in lines] == [o["id"] for o in OFFERS]   # every workflow the agent may use is still there
    full = {line["id"] for line in lines if "settings" in line}
    assert full == {"image/flux", "image/krea"}
    video = lines[0]
    assert video == {"id": "video/h3_all_in_one", "title": "H3_All_In_One", "makes": "video", "about": OFFERS[0]["about"][:120],
                     "pick_when": "Long shots with a cast.", "default": True}
    assert "workflow_info" in dict(parts)["workflows"].splitlines()[0]
    assert "prompting" not in dict(parts)   # the video model's prompt guide goes with its workflow only when it is shown
    everything = agent.question_parts("Make a picture of a red kite", OFFERS, [], "video/h3_all_in_one")
    assert all("settings" in json.loads(line) for line in _workflows(everything))   # detailed=None: as before, all in full
    assert dict(everything)["workflows"].startswith("Workflows:\n") and "minimax-h3" in dict(everything)["prompting"]
    assert len(dict(parts)["workflows"]) < len(dict(everything)["workflows"])


def test_workflow_info_gives_one_in_full_with_its_prompt_guide():
    found = agent.workflow_info(OFFERS, " video/h3_all_in_one ")
    offer, guide = found.split("\n\n", 1)
    assert json.loads(offer) == OFFERS[0] and guide.startswith(agent.PROMPT_GUIDES)
    assert prompters.part(["video/h3_all_in_one"]) in guide
    assert agent.workflow_info(OFFERS, "image/flux") == json.dumps(OFFERS[1])   # no guide: the workflow alone
    missing = agent.workflow_info(OFFERS, "video/nope")
    assert missing.startswith("There is no workflow \"video/nope\"") and "image/krea" in missing
    assert "workflow_info" in agent.native_tools(agent.TOOLS)


def _turn(client, monkeypatch, body):
    seen = {}

    async def fake_tools(system, message, workflow_ids, tools, finishing=None, model=None, rounds=0, thread=None, web=False, reply_chars=0):
        seen.update(message=message, ids=workflow_ids, info=await tools["workflow_info"]({"op": "video/h3_all_in_one"}))
        return {"thought": "", "reply": "Fine.", "steps": [], "tokens": {}}

    async def fake_ask(system, message, workflow_ids, history=(), model=None, thread=None):
        seen.update(message=message, ids=workflow_ids)
        return {"thought": "", "reply": "Fine.", "steps": [], "tokens": {}}

    async def fake_describe(state, user_id, entries, **kwargs):
        return 0
    monkeypatch.setattr(client.app.state.agent, "ask_with_tools", fake_tools)
    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    monkeypatch.setattr(workspace.memory, "describe_missing", fake_describe)
    plan = client.post("/api/agent/plan", json=body)
    assert plan.status_code == 200, plan.text
    workflows = seen["message"].split("\n\nWorkflows", 1)[1].split("\n\n", 1)[0].splitlines()[1:]
    return seen, {json.loads(line)["id"]: json.loads(line) for line in workflows}, plan.json()


def test_a_message_about_a_picture_gets_the_picture_workflows_in_full_and_the_rest_on_demand(client, monkeypatch):
    register(client)
    seen, listed, plan = _turn(client, monkeypatch, {"instruction": "Make a picture of a red kite over green hills"})
    assert set(listed) <= set(seen["ids"]) and "video/h3_all_in_one" in listed   # the agent still knows every workflow
    assert all("settings" in o or "references" in o or "prompt_tips" in o for wid, o in listed.items() if wid.startswith("image/"))
    assert set(listed["video/h3_all_in_one"]) <= {"id", "title", "makes", "about", "pick_when", "default"}
    assert "(prompt_guide minimax-h3;" not in seen["message"]   # the video model's long prompt guide stays out
    # ...and is there in full, guide and all, when the agent asks for it
    whole = json.loads(seen["info"].split("\n\n", 1)[0])
    assert whole["id"] == "video/h3_all_in_one" and "references" in whole and "(prompt_guide minimax-h3;" in seen["info"]
    assert ("activity", "plan", "Read the workflow video/h3_all_in_one") in [(e["type"], e.get("icon"), e.get("text")) for e in plan["activity"]]


def test_a_message_that_does_not_say_or_has_no_tools_gets_every_workflow_in_full(client, monkeypatch):
    register(client)
    for body in ({"instruction": "go ahead"}, {"instruction": "Make a picture of a kite", "tools": False}):
        seen, listed, _ = _turn(client, monkeypatch, body)
        assert set(listed) <= set(seen["ids"])
        assert "settings" in listed["video/h3_all_in_one"] and "(prompt_guide minimax-h3;" in seen["message"]


def test_the_answers_shape_names_the_same_workflows_whatever_this_message_is_offered(client, monkeypatch):
    """The shape of Claude's answer named only the workflows offered to the message, and its session is opened again (a
    new Claude Code process) whenever that shape changes: a picture attached, or a workflow named, did it."""
    import asyncio as _asyncio
    from scene import media as _media
    me = register(client)
    plain, listed_plain, _ = _turn(client, monkeypatch, {"instruction": "Make a picture of a red kite"})
    folder = client.app.state.outputs.folder(me["id"])
    folder.mkdir(parents=True)
    _asyncio.run(_media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=blue:s=64x64", "-frames:v", "1", folder / "kite.png"))
    kite = client.app.state.db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
                                   "VALUES (?, 'upload/file', 'image', 'kite', 'kite.png', '{}', '{}', 1)", (me["id"],))
    attached, listed_attached, _ = _turn(client, monkeypatch, {"instruction": "Make a video of this kite", "selection": [kite]})
    assert set(listed_plain) < set(listed_attached)   # a picture to work from: more workflows are offered...
    assert plain["ids"] == attached["ids"] == sorted(plain["ids"])   # ...and the answer's shape is the same
    assert set(listed_plain) | set(listed_attached) <= set(plain["ids"])

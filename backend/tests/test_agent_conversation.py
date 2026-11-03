"""The agent's conversation: what it did and thought for a plan (also as a live stream), the pictures its replies name,
the frames shown under a result and the thumbs on a result."""

import asyncio
import json
import math

from scene import agent, media, memory
from scene.api import workspace
from test_api import console, register

STEP = {"tool": "generate", "workflow": "video/h3_all_in_one", "name": "Dog in the park", "prompt": "A dog runs across a park.",
        "duration": 6, "resolution": 480, "orientation": "portrait"}


def item(client, user_id, name, kind="image", filename="missing", rating=0):
    return client.app.state.db.run(
        "INSERT INTO generations (user_id, workflow, kind, name, filename, summary, settings, context, created, about, rating) "
        "VALUES (?, 'x/y', ?, ?, ?, '', '{}', '{}', 1, 'A brown dog on grass.', ?)", (user_id, kind, name, filename, rating))


def model(monkeypatch, client, *answers, looked=0):
    """The agent's model answers these, in turn; describing pictures is said to have looked at `looked` of them."""
    asked = []

    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        asked.append(message)
        answer = answers[min(len(asked), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def fake_describe(state, user_id, entries, **kwargs):
        return looked
    monkeypatch.setattr(client.app.state.agent, "ask", fake_ask)
    monkeypatch.setattr(workspace.memory, "describe_missing", fake_describe)
    return asked


def test_a_plan_comes_with_what_the_agent_did_and_thought(client, monkeypatch):
    me = register(client)
    dog = item(client, me["id"], "Brown dog")
    model(monkeypatch, client, {"thought": "A pet shop ad: one 6 s portrait shot of a dog.",
                                "reply": "One shot of **the dog** [[item:%d]] and [[item:99999]] [[asset:77]]." % dog,
                                "steps": [STEP, dict(STEP, name="Bad", workflow="video/nope")]}, looked=2)
    plan = client.post("/api/agent/plan", json={"instruction": "a short ad for a pet shop"}).json()
    assert plan["thought"] == "A pet shop ad: one 6 s portrait shot of a dog." and plan["seconds"] >= 0
    said = [(e["type"], e.get("icon"), e.get("text")) for e in plan["activity"]]
    assert ("activity", "book", "Opened NeuralCore: 1 entry") in said
    assert ("activity", "look", "Looked at 2 new pictures") in said
    assert ("activity", "skill", "Read the skill “An ad, a promo or a product video”") in said
    assert ("activity", "skip", "Left out “Bad”: there is no workflow “video/nope” it can use") in said
    assert said[-1] == ("activity", "plan", "Checked and priced 1 step")
    thought = next(e for e in plan["activity"] if e["type"] == "thought")
    assert thought["text"].startswith("A pet shop ad") and thought["seconds"] >= 0
    # an item the model was given becomes a small picture, with its studio link; ids it made up are taken out, and said
    public = client.app.state.db.one("SELECT public_id FROM generations WHERE id = ?", (dog,))["public_id"]
    assert plan["chips"] == {"item:%d" % dog: {"name": "Brown dog", "kind": "image", "link": "/api/m/" + public}}
    assert "[[item:%d]]" % dog in plan["reply"] and "99999" not in plan["reply"] and "asset:77" not in plan["reply"]
    assert plan["reply"].endswith(agent.MISSING)
    assert [s["name"] for s in plan["steps"]] == ["Dog in the park"]


def test_the_film_a_long_run_made_is_handed_over_when_asked(client, monkeypatch):
    me = register(client)
    film = client.post("/api/projects", json={"name": "Ep 6"}).json()["id"]
    db = client.app.state.db
    made = db.run("INSERT INTO generations (user_id, project_id, workflow, kind, name, filename, summary, settings, context, run, created) "
                  "VALUES (?, ?, 'edit/film', 'video', 'Film on the master audio', 'f.mp4', '', '{}', '{}', 'abcdefghijkl', 2)", (me["id"], film))
    trim = db.run("INSERT INTO generations (user_id, project_id, workflow, kind, name, filename, summary, settings, context, run, created) "
                  "VALUES (?, ?, 'edit/trim', 'video', 'Trim to frames', 't.mp4', '', '{}', '{}', 'abcdefghijkl', 3)", (me["id"], film))
    elsewhere = item(client, me["id"], "Not in this project")
    asked = model(monkeypatch, client, {"thought": "They want the film.", "steps": [],
                                        "reply": "Here it is:\n[[show:item:%d]]\n[[item:%d]] [[item:%d]]" % (made, trim, elsewhere)})
    plan = client.post("/api/agent/plan", json={"instruction": "give me the final video here", "project_id": film}).json()
    # the whole film is among the recent items the model is given, the run's working files are not
    assert '"id": %d' % made in asked[0] and '"id": %d' % trim not in asked[0]
    assert plan["chips"]["item:%d" % made]["name"] == "Film on the master audio"
    assert plan["chips"]["item:%d" % made]["link"].startswith("/api/m/")
    assert "item:%d" % trim in plan["chips"]   # named by its id: of this project, so shown
    assert "item:%d" % elsewhere not in plan["chips"] and plan["reply"].endswith(agent.MISSING)


def test_a_second_try_is_in_the_log(client, monkeypatch):
    register(client)
    model(monkeypatch, client, {"thought": "First go.", "reply": "Generating the clip now.", "steps": []},
          {"thought": "Planned it this time.", "reply": "Here is the shot.", "steps": [STEP]})
    plan = client.post("/api/agent/plan", json={"instruction": "generate a dog clip"}).json()
    kinds = [(e["type"], e.get("icon")) for e in plan["activity"]]
    assert kinds.count(("thought", None)) == 2 and ("activity", "retry") in kinds
    assert plan["thought"] == "Planned it this time." and len(plan["steps"]) == 1


def stream(client, body):
    response = client.post("/api/agent/plan", json=body, headers={"Accept": "application/x-ndjson"})
    return response, [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_the_plan_streams_as_the_agent_works(client, monkeypatch):
    register(client)
    model(monkeypatch, client, {"thought": "A dog shot.", "reply": "Here it is.", "steps": [STEP]})
    response, events = stream(client, {"instruction": "a dog in a park"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/x-ndjson")
    types = [e["type"] for e in events]
    assert types[-1] == "plan" and "status" in types and types.index("status") < types.index("thought")
    plan = events[-1]
    assert plan["steps"][0]["name"] == "Dog in the park" and [e["type"] for e in plan["activity"]][-1] == "activity"
    # what goes wrong once the stream has started arrives as its last line
    model(monkeypatch, client, agent.AgentError("The agent's model server (Ollama) can't be reached."))
    response, events = stream(client, {"instruction": "a dog in a park"})
    assert response.status_code == 200 and events[-1] == {"type": "error", "message": "The agent's model server (Ollama) can't be reached."}
    # and a message that can't be planned at all is refused before the stream starts
    assert client.post("/api/agent/plan", json={"instruction": " "}, headers={"Accept": "application/x-ndjson"}).status_code == 400


def test_a_video_shows_its_frames_and_a_result_can_be_rated(client):
    me = register(client)
    folder = client.app.state.outputs.folder(me["id"])
    folder.mkdir(parents=True)
    asyncio.run(media._ffmpeg("-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x48:d=2:r=24", "-pix_fmt", "yuv420p", folder / "clip.mp4"))
    clip = item(client, me["id"], "Clip", kind="video", filename="clip.mp4")
    still = item(client, me["id"], "Still")
    frame = client.get("/api/library/%d/frame?at=1" % clip)
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg" and frame.content[:2] == b"\xff\xd8"
    assert (folder / ".posters" / "clip.mp4.10.jpg").is_file()   # kept for the next time
    assert client.get("/api/library/%d/frame?at=0" % clip).status_code == 200
    assert client.get("/api/library/%d/frame" % still).status_code == 400
    assert client.get("/api/library/%d/frame" % (clip + 999)).status_code == 404

    assert client.put("/api/library/%d" % clip, json={"rating": 1}).status_code == 200
    assert client.put("/api/library/%d" % still, json={"rating": -1}).status_code == 200
    rated = {i["name"]: i["rating"] for i in client.get("/api/library").json()["items"]}
    assert rated == {"Clip": 1, "Still": -1}
    for wrong in (5, True, "1"):
        assert client.put("/api/library/%d" % clip, json={"rating": wrong}).status_code == 400
    # the agent's book says which were liked: it reuses those and never the ones turned down
    book = {e["name"]: e for e in memory.book_for_model(memory.book(client.app.state.db, me["id"], 0))}
    assert book["Clip"].get("liked") is True and book["Still"].get("disliked") is True and "liked" not in book["Still"]


def test_a_message_costs_what_its_model_costs(client, monkeypatch):
    me = register(client)
    prices = console(client).put("/api/admin/pricing/llm", json={"model": "gemini/flash", "credits": 3}).json()
    assert {"model": "gemini/flash", "credits": 3, "available": False, "tokens": None} in prices["models"]
    assert console(client).put("/api/admin/pricing/llm", json={"model": "local:9b", "credits": 1}).status_code == 200
    assert console(client).put("/api/admin/pricing/llm", json={"model": "x", "credits": 1.5}).status_code == 400   # whole credits only
    assert console(client).put("/api/admin/pricing/llm", json={"model": "", "credits": 1}).status_code == 400

    async def pick(wanted=None):
        return wanted or "gemini/flash"
    monkeypatch.setattr(client.app.state.agent, "pick_model", pick)
    model(monkeypatch, client, {"thought": "", "reply": "Hello.", "steps": [], "model": "gemini/flash"},
          {"thought": "", "reply": "Hello again.", "steps": [], "model": "local:9b"})
    plan = client.post("/api/agent/plan", json={"instruction": "hi"}).json()
    assert plan["llm"] == {"credits": 3, "model": "gemini/flash"} and plan["balance"] == 497
    # a busy model stood in for: the message costs what the model that answered costs
    plan = client.post("/api/agent/plan", json={"instruction": "hi"}).json()
    assert plan["llm"] == {"credits": 1, "model": "local:9b"} and plan["balance"] == 496
    # without enough credits for the chosen model, the model is not asked
    client.app.state.db.run("UPDATE users SET credits = 2 WHERE id = ?", (me["id"],))
    refused = client.post("/api/agent/plan", json={"instruction": "hi"})
    assert refused.status_code == 400 and "costs 3 cr" in refused.json()["detail"]
    # a free model costs nothing
    assert console(client).put("/api/admin/pricing/llm", json={"model": "gemini/flash", "credits": 0}).status_code == 200
    model(monkeypatch, client, {"thought": "", "reply": "Hello.", "steps": [], "model": "gemini/flash"})
    assert client.post("/api/agent/plan", json={"instruction": "hi"}).json()["llm"]["credits"] == 0


def test_a_message_to_claude_costs_the_tokens_it_used(client, monkeypatch):
    me = register(client)
    credits = client.app.state.credits
    # 1,000 fresh, 9,000 written to the cache, 90,000 read from it and 2,000 written out, at Opus 5.5's prices:
    # $0.004 + $0.072 + $0.018 + $0.04 = $0.134, at ₹88 a dollar ₹11.79, at ₹100 for 1,000 credits 118 credits
    used = {"prompt": 100_000, "cached": 90_000, "written": 9_000, "answer": 2_000}
    assert credits.token_cost("claude/opus", used) == 118
    assert credits.token_cost("claude/claude-opus-4-8", used) == math.ceil((5_000 + 90_000 + 45_000 + 50_000) / 1e6 * 88 * 10)
    assert credits.token_cost("claude/haiku", used) == 4   # $0.0037: a credit at least
    assert credits.token_cost("gemini/flash", used) == 0 and credits.token_cost("local:9b", used) == 0
    assert credits.token_cost("claude/opus", {}) == 0

    async def pick(wanted=None):
        return wanted or "claude/opus"
    monkeypatch.setattr(client.app.state.agent, "pick_model", pick)
    model(monkeypatch, client, {"thought": "", "reply": "Hello.", "steps": [], "model": "claude/opus", "tokens": used})
    plan = client.post("/api/agent/plan", json={"instruction": "hi"}).json()
    assert plan["llm"] == {"credits": 118, "model": "claude/opus"} and plan["balance"] == 500 - 118
    # the rupees a dollar buys are the admin's to set
    assert console(client).put("/api/admin/pricing", json={"inr_per_usd": 44}).json()["inr_per_usd"] == 44
    assert credits.token_cost("claude/opus", used) == 59
    llm = console(client).get("/api/admin/pricing/llm").json()
    assert llm["inr_per_usd"] == 44
    # the tokens were used already: a user with fewer credits than they cost gives all they have, then is refused
    client.app.state.db.run("UPDATE users SET credits = 20 WHERE id = ?", (me["id"],))
    plan = client.post("/api/agent/plan", json={"instruction": "hi"}).json()
    assert plan["llm"]["credits"] == 20 and plan["balance"] == 0
    refused = client.post("/api/agent/plan", json={"instruction": "hi"})
    assert refused.status_code == 400 and "charged by the tokens" in refused.json()["detail"]
    # a flat price set in the console is charged in the place of the tokens
    client.app.state.db.run("UPDATE users SET credits = 100 WHERE id = ?", (me["id"],))
    assert console(client).put("/api/admin/pricing/llm", json={"model": "claude/opus", "credits": 5}).status_code == 200
    assert client.post("/api/agent/plan", json={"instruction": "hi"}).json()["llm"] == {"credits": 5, "model": "claude/opus"}


def test_the_conversation_keeps_many_turns_with_what_each_used_and_drops_the_oldest_past_its_budget():
    from scene import agent
    history = [{"instruction": "turn {}".format(i), "reply": "answer {}".format(i)} for i in range(30)]
    history[0]["steps"] = [{"name": "Maya", "uses": []}, "Liam"]   # the old shape (a name) is still read
    history[-1]["steps"] = [{"name": "Football Match Beat", "uses": ["Maya", "Liam", "Elena"]}]
    turns = agent.past_turns(history)
    assert len(turns) == 60 and turns[0]["content"] == "turn 0"   # far more than the six turns of before
    assert "(Planned: Maya, Liam)" in turns[1]["content"]
    assert "(Planned: Football Match Beat using Maya, Liam, Elena)" in turns[-1]["content"]
    long = [{"instruction": "x" * 2000, "reply": "y" * 1500} for _ in range(40)]
    kept = agent.past_turns(long)
    assert sum(len(t["content"]) for t in kept) <= agent.HISTORY_CHARS and len(kept) % 2 == 0 and kept[-1]["content"] == "y" * 1500


def test_the_direction_goes_with_a_message_and_comes_back_updated(client, monkeypatch):
    register(client)
    asked = model(monkeypatch, client, {"thought": "", "reply": "Noted.", "steps": [], "direction": "Film: a pet shop ad\n1. dog in park"})
    plan = client.post("/api/agent/plan", json={"instruction": "hello", "direction": "Film: a pet shop ad"}).json()
    assert "Film: a pet shop ad" in asked[0] and "Direction, the notes" in asked[0]
    assert plan["direction"] == "Film: a pet shop ad\n1. dog in park"


def test_compact_folds_the_conversation_into_a_direction(client, monkeypatch):
    register(client)
    seen = []

    async def fake_chat(messages, answer_format, **kwargs):
        seen.append(messages[-1]["content"])
        return {"direction": "  Film: pet ad  \n2. cat  "}
    monkeypatch.setattr(client.app.state.agent, "chat", fake_chat)
    history = [{"instruction": "a pet shop ad", "reply": "Here is a plan.", "steps": []}]
    done = client.post("/api/agent/compact", json={"history": history, "direction": "old notes"}).json()
    assert done["direction"] == "Film: pet ad\n2. cat"
    assert "old notes" in seen[0] and "a pet shop ad" in seen[0]
    assert client.post("/api/agent/compact", json={"history": []}).status_code == 400

"""The creative director (docs/creative-director.md): the big job, its brief, its concept, its stills first and the
second opinion the studio asks for itself."""

from scene import agent, core, guardrails
from test_agent_conversation import STEP
from test_agent_memory import film
from test_agent_shots import hosted
from test_api import register


def told(seen):
    return [m["content"] for m in seen[-1] if m["role"] == "user"]


def shots(n, **more):
    return [dict(STEP, name="Shot {}".format(i), shot_number=i, **more) for i in range(1, n + 1)]


BRIEF_CARD = {"text": "Who is it for?", "options": ["Students", "Office workers"], "default": "Students", "details": []}


# ---------------------------------------------------------------- what a big job is

def test_a_big_job_is_more_than_four_shots_a_price_over_the_limit_or_a_message_asking_for_many():
    assert not agent.big_job(shots(4)) and agent.big_job(shots(5))
    # the studio's priced steps: a shot's variations count once, edits and the cut never
    priced = [{"name": "a", "credits": 100, "settings": {"workflow": "video/x"}, "kind": "video"},
              {"name": "a", "credits": 100, "settings": {"workflow": "video/x"}, "kind": "video", "variation": {"n": 2, "of": 2}},
              {"name": "cut", "credits": 0, "settings": None, "assemble": {"clips": []}, "kind": "video"}]
    assert len(agent.generated(priced)) == 1
    assert agent.big_job(priced, credits=150) and not agent.big_job(priced, credits=300) and not agent.big_job(priced, credits=0)
    assert agent.big_job([], "a 20-shot ad for my gym") and agent.big_job([], "make it 6 scenes") and not agent.big_job([], "3 shots")
    assert agent.big_job([], "yes, portrait", [{"instruction": "a 12 shot film of the monsoon"}])
    assert not agent.big_job([], "a 1080p picture of a cat")   # a number that is not a count of shots


def test_the_big_job_limit_is_a_guardrail_in_its_range(client):
    db = client.app.state.db
    shown = guardrails.shown(db)
    assert shown["limits"]["creative_big_job_credits"] == 600 and shown["ranges"]["creative_big_job_credits"] == [0, 10_000_000]
    guardrails.save(db, {"limits": {"creative_big_job_credits": 0}})
    assert guardrails.limit(db, "creative_big_job_credits") == 0
    try:
        guardrails.save(db, {"limits": {"creative_big_job_credits": -5}})
        assert False, "a negative limit was taken"
    except ValueError as error:
        assert "creative_big_job_credits" in str(error)


def test_stills_come_first_for_a_big_video_job_unless_neuralcore_has_them_or_the_user_skips_them():
    video = [{"name": "s", "kind": "video", "credits": 100, "settings": {"workflow": "video/x"}, "start": None}] * 5
    still = [{"name": "k", "kind": "image", "credits": 40, "settings": {"workflow": "image/x"}, "start": None}]
    assert agent.stills_wanted(video)
    assert not agent.stills_wanted(still + video)                                         # the stills come first
    assert not agent.stills_wanted(video, [{"asset": 3, "kind": "image", "type": "character"}])   # NeuralCore has them
    assert agent.stills_wanted(video, [{"asset": 3, "kind": "image", "type": "prop"}])
    assert not agent.stills_wanted(video, (), "skip the stills, go straight to video")
    assert not agent.stills_wanted(still)                                                 # no video: nothing to say


# ---------------------------------------------------------------- the brief, the concept, the second opinion

def test_a_big_job_without_a_brief_is_sent_back_once_to_ask_for_one(client, monkeypatch):
    register(client)
    asked = []

    async def opinion(*args, **kwargs):
        asked.append(kwargs)
        return {"critique": "x", "model": "claude/opus", "tokens": {}}
    monkeypatch.setattr(client.app.state.agent, "second_opinion", opinion)
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Five shots.", "steps": shots(5)},
                  {"tool": "finish", "reply": "A few things first.", "steps": [], "questions": [BRIEF_CARD]})
    plan = client.post("/api/agent/plan", json={"instruction": "an ad for my cafe", "project_id": film(client)}).json()
    assert plan["steps"] == [] and [q["text"] for q in plan["questions"]] == ["Who is it for?"]
    assert any("no brief yet (/brief is empty)" in t for t in told(seen)) and len(seen) == 2
    assert not asked   # no second opinion on a plan sent back for its brief
    assert any("with no brief yet" in e["text"] for e in plan["activity"] if e["type"] == "activity")


def test_a_briefed_big_job_gets_the_studios_notes_once_and_keeps_its_concept(client, monkeypatch):
    me = register(client)
    project = film(client)
    core.Core(client.app.state.db, me["id"], "", project).write("/brief", {"audience": "students", "platform": "Reels"})
    asked = []

    async def opinion(about, pictures=(), labels=(), model=None, purpose="second_opinion"):
        asked.append((about, purpose))
        return {"critique": "Open on the face, not the street.", "model": "claude/opus", "tokens": {}}
    monkeypatch.setattr(client.app.state.agent, "second_opinion", opinion)
    concept = "A rainy-night chase that ends at the warmest table in town."
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Five shots.", "steps": shots(5), "concept": ""},
                  {"tool": "finish", "reply": concept + " Five shots.", "steps": shots(5), "concept": concept})
    plan = client.post("/api/agent/plan", json={"instruction": "an ad for my cafe", "project_id": project}).json()
    notes = told(seen)[-1]
    assert notes.startswith("Before the user sees this plan, the studio's notes on it")
    assert "A senior creative director reviewed your plan: Open on the face, not the street." in notes
    assert "Revise if it helps; you decide." in notes and "needs its concept" in notes and "key stills first" in notes
    assert len(seen) == 2 and len(asked) == 1 and asked[0][1] == agent.AUTO_OPINION   # once a message, written down as auto
    assert "students" in asked[0][0] and "Shot 1" in asked[0][0]                        # the plan and its brief, in words
    assert len(plan["steps"]) == 5 and plan["concept"] == concept
    kept = core.Core(client.app.state.db, me["id"], "", project).read("/concept")
    assert kept["value"] == concept


def test_a_small_job_gets_no_question_no_hint_and_no_second_opinion(client, monkeypatch):
    register(client)
    asked = []

    async def opinion(*args, **kwargs):
        asked.append(True)
        return {"critique": "x", "model": "claude/opus", "tokens": {}}
    monkeypatch.setattr(client.app.state.agent, "second_opinion", opinion)
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "One shot.", "steps": shots(1)})
    plan = client.post("/api/agent/plan", json={"instruction": "a dog runs across a park", "project_id": film(client)}).json()
    assert len(plan["steps"]) == 1 and len(seen) == 1 and not asked and plan["concept"] == ""


def test_without_memory_the_brief_is_a_line_of_the_direction(client, monkeypatch):
    register(client)

    async def opinion(*args, **kwargs):
        raise agent.AgentError("busy")   # a second opinion that fails is left out, quietly
    monkeypatch.setattr(client.app.state.agent, "second_opinion", opinion)
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Five.", "steps": shots(5), "concept": "One idea."})
    plan = client.post("/api/agent/plan", json={"instruction": "a reel", "direction": "Brief: students; Reels; warm."}).json()
    assert not any("no brief yet" in t for t in told(seen)) and len(plan["steps"]) == 5
    assert any("No automatic second opinion" in e["text"] for e in plan["activity"] if e["type"] == "activity")


# ---------------------------------------------------------------- the craft library and the gold examples

def test_every_craft_note_has_its_header_and_is_short_and_dense():
    from scene import craft_library
    found = craft_library.notes()
    assert len(found) >= 14
    for note in found:
        assert note["id"] and note["title"] and note["tags"] and note["when"], note["id"]
        assert 300 <= len(note["text"].split()) <= 900, (note["id"], len(note["text"].split()))
    ids = {n["id"] for n in found}
    assert {"social-hooks", "ad-structures", "shot-grammar", "screen-direction", "camera-moves", "lighting", "colour", "pacing",
            "genres", "product-shots", "character-consistency", "type-and-motion", "platform-specs", "model-limits"} <= ids


def test_craft_search_ranks_the_notes_by_their_words_and_tags():
    from scene import craft_library
    assert craft_library.search("an ad for my cafe on reels")[0]["id"] == "ad-structures"
    assert craft_library.search("her fingers look melted")[0]["id"] == "model-limits"
    assert craft_library.search("what aspect ratio for tiktok")[0]["id"] == "platform-specs"
    assert craft_library.search("anything", tags=["horror"])[0]["id"] == "genres"
    assert len(craft_library.search("hook reels camera light colour pacing")) <= craft_library.MOST_NOTES
    assert craft_library.search("") == [] and "No craft note fits" in craft_library.for_tool("zzqx")


def test_the_gold_examples_are_25_drafts_and_a_rejected_one_is_never_used(tmp_path):
    import json
    from scene import craft_library
    found = craft_library.examples()
    assert len(found) == 25 and {e["status"] for e in found} == {"draft"}
    for e in found:
        assert e["brief"] and e["concept"] and e["plan_outline"] and e["why"] and e["tags"], e["id"]
        assert set(e["context"]) == {"platform", "audience"}
    assert any("hindi" in e["tags"] for e in found) and any("spanish" in e["tags"] for e in found)
    assert craft_library.closest("an ad for my cafe")[0]["id"] == "cafe-rainy-morning-reel"
    for status, name in (("approved", "good"), ("rejected", "bad"), ("draft", "maybe")):
        (tmp_path / (name + ".json")).write_text(json.dumps({"id": name, "status": status, "brief": "a cafe ad", "concept": "c",
                                                              "plan_outline": ["1. shot"], "why": ["w"], "tags": ["cafe"]}), encoding="utf-8")
    assert sorted(e["id"] for e in craft_library.closest("a cafe ad", 5, tmp_path)) == ["good", "maybe"]
    assert craft_library.examples_part("a cafe ad", 2, tmp_path).startswith("Examples of strong work (adapt, never copy):")


def test_a_message_that_looks_big_comes_with_its_craft_note_and_examples_and_a_small_one_does_not(client, monkeypatch):
    register(client)
    seen = hosted(monkeypatch, client, {"tool": "craft_search", "query": "cafe ad hook", "tags": ["reels"]},
                  {"tool": "finish", "reply": "Hi.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "an ad for my cafe"})
    given = told(seen)
    assert any("Craft note that fits this job: ad-structures" in t and "Examples of strong work (adapt, never copy)" in t
               and "Brief: an ad for my cafe" in t for t in given)
    assert any(t.startswith("Result of craft_search:") and "Craft note ad-structures" in t for t in given)
    system = seen[-1][0]["content"]
    assert "Craft library: craft_search" in system and "Examples of strong work" not in system.split("Craft library")[0]
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "One.", "steps": []})
    client.post("/api/agent/plan", json={"instruction": "a picture of a cat on a windowsill"})
    assert not any("Examples of strong work" in t for t in told(seen))

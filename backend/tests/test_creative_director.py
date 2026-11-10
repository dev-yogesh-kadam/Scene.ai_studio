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


# ---------------------------------------------------------------- the content check

def checked_by(monkeypatch, client, verdict):
    """The fast model's content check answers `verdict` (or raises it, when it is an exception); returns the calls."""
    calls = []

    async def check_content(system, message, shape):
        calls.append(message)
        if isinstance(verdict, Exception):
            raise verdict
        return verdict
    monkeypatch.setattr(client.app.state.agent, "check_content", check_content)
    return calls


def test_a_flag_of_warn_is_a_note_on_the_plan_card_and_is_written_down(client, monkeypatch):
    from scene import content_check
    content_check.SEEN.clear()
    me = register(client)
    calls = checked_by(monkeypatch, client, {"flag": "warn", "categories": ["real_person"], "note": "This looks like a real actor."})
    hosted(monkeypatch, client, {"tool": "finish", "reply": "One shot.", "steps": [dict(STEP, prompt="A famous actor waves.")]})
    plan = client.post("/api/agent/plan", json={"instruction": "a famous actor waving"}).json()
    assert len(plan["steps"]) == 1 and plan["content_note"] == "This looks like a real actor."
    assert "A famous actor waves." in calls[0] and "a famous actor waving" in calls[0]
    row = client.app.state.db.one("SELECT * FROM moderation WHERE kind = 'content_check'")
    assert row["verdict"] == "warn" and row["words"] == "real_person" and row["user_id"] == me["id"]
    # keeping the same plan does not ask again: its verdict is remembered
    client.post("/api/agent/plans", json={"steps": plan["steps"]})
    assert len(calls) == 1


def test_a_block_refuses_the_plan_only_in_the_mode_that_blocks(client, monkeypatch):
    from scene import content_check
    content_check.SEEN.clear()
    register(client)
    checked_by(monkeypatch, client, {"flag": "block", "categories": ["minors"], "note": "Nothing sexual involving a child."})
    hosted(monkeypatch, client, {"tool": "finish", "reply": "One shot.", "steps": [STEP]})
    plan = client.post("/api/agent/plan", json={"instruction": "x"}).json()   # the default mode, warn: a note only
    assert len(plan["steps"]) == 1 and plan["content_note"] == "Nothing sexual involving a child."
    guardrails.save(client.app.state.db, {"choices": {"content_check_mode": "block"}})
    content_check.SEEN.clear()
    plan = client.post("/api/agent/plan", json={"instruction": "x"}).json()
    assert plan["steps"] == [] and plan["reply"] == "This plan can't be made here: Nothing sexual involving a child."
    refused = client.post("/api/agent/plans", json={"steps": [{"name": "x", "kind": "video", "settings": {"prompt": "y"}}]})
    assert refused.status_code == 400 and "can't be made here" in refused.json()["detail"]


def test_the_check_fails_open_and_is_off_when_switched_off(client, monkeypatch):
    from scene import content_check
    content_check.SEEN.clear()
    register(client)
    calls = checked_by(monkeypatch, client, agent.AgentError("Claude is busy"))
    hosted(monkeypatch, client, {"tool": "finish", "reply": "One shot.", "steps": [STEP]})
    plan = client.post("/api/agent/plan", json={"instruction": "x"}).json()
    assert len(plan["steps"]) == 1 and plan["content_note"] == ""
    assert any("content check could not run" in e["text"] for e in plan["activity"] if e["type"] == "activity")
    assert content_check.status()["error"] == "Claude is busy"
    assert client.app.state.db.one("SELECT COUNT(*) AS n FROM moderation")["n"] == 0
    guardrails.save(client.app.state.db, {"choices": {"content_check_mode": "off"}})
    client.post("/api/agent/plan", json={"instruction": "x"})
    assert len(calls) == 1   # off: no call at all


def test_the_content_check_mode_is_a_choice_of_three_words(client):
    db = client.app.state.db
    shown = guardrails.shown(db)
    assert shown["choices"] == {"content_check_mode": "warn"} and shown["options"]["content_check_mode"] == ["off", "warn", "block"]
    for wrong in ({"content_check_mode": "loud"}, {"nope": "warn"}):
        try:
            guardrails.save(db, {"choices": wrong})
            assert False, wrong
        except ValueError:
            pass
    assert guardrails.save(db, {"choices": {"content_check_mode": "block"}})["choices"]["content_check_mode"] == "block"


def test_the_content_check_reads_drawn_words_and_what_the_user_supplied():
    from scene import content_check
    steps = [{"name": "Card", "motion": {"scenes": [{"heading": "Big sale", "text": "Today"}]}},
             {"name": "Shot", "settings": {"prompt": "She waves."}, "uses": [{"name": "Maya", "label": "Character"}]}]
    words = content_check.plan_words(steps)
    assert "Big sale" in words and "She waves." in words and content_check.supplied(steps) == ["Maya (Character)"]
    assert content_check.clean({"flag": "warn", "categories": ["real_person", "made_up"], "note": " a\nnote "}) == {
        "flag": "warn", "categories": ["real_person"], "note": "a note"}
    assert content_check.clean({"flag": "maybe"})["flag"] == "none"
    assert content_check.applied({"flag": "block", "categories": [], "note": "n"}, "warn")["flag"] == "warn"


def test_the_console_checks_show_the_content_check_and_the_gates(client):
    import asyncio
    from scene import health
    found = health.creative(client.app.state)
    assert found["content_check"]["mode"] == "warn" and "shot variety" in found["gates"]


# ---------------------------------------------------------------- the quality gates

def shot(name, prompt="A dog runs.", **more):
    return dict({"tool": "generate", "workflow": "video/h3_all_in_one", "name": name, "prompt": prompt}, **more)


def test_the_continuity_gate_finds_a_place_or_a_person_written_two_ways():
    same = "A girl of about twenty with a black braid and a yellow raincoat"
    assert guardrails.continuity_gate([shot("a", same + " runs.", place="rainy night market"),
                                       shot("b", same + " jumps.", place="rainy night market")]) is None
    found = guardrails.continuity_gate([shot("a", same + " runs.", place="rainy night market"),
                                        shot("b", "A girl in a red coat jumps.", place="the night market in the rain")])
    assert "written two ways" in found and "the girl is described differently" in found and "red coat" in found
    # a reference carries the look, and an always-on character in NeuralCore too
    assert guardrails.continuity_gate([shot("a", same + " runs."), shot("b", "A girl in a red coat jumps.", uses=[{"item": 3}])]) is None
    assert guardrails.continuity_gate([shot("a", same + " runs."), shot("b", "A girl in a red coat jumps.")],
                                      [{"type": "character", "always": True, "name": "Maya"}]) is None
    assert guardrails.continuity_gate([shot("a", place="Meera's kitchen"), shot("b", place="Meera's kitchen, next morning")]) is None


def test_the_variety_gate_wants_more_than_one_shot_size():
    assert "every shot is MS" in guardrails.variety_gate([shot(n, shot_size="MS") for n in "abc"])
    assert guardrails.variety_gate([shot("a", shot_size="WS"), shot("b", shot_size="MS"), shot("c", shot_size="MS")]) is None
    assert guardrails.variety_gate([shot(n, shot_size="MS") for n in "ab"]) is None       # two shots: not judged
    assert guardrails.variety_gate([shot(n) for n in "abcd"]) is None                      # no sizes given: not judged


def test_the_hook_gate_wants_a_social_video_to_open_on_a_hook():
    flat = [shot("Street", "A quiet street at dawn.", shot_size="WS", move="static", orientation="portrait"), shot("b")]
    assert "first one or two seconds" in guardrails.hook_gate(flat)
    assert guardrails.hook_gate([dict(flat[0], orientation="landscape"), flat[1]]) is None          # not social
    assert "first one or two seconds" in guardrails.hook_gate([dict(flat[0], orientation="landscape"), flat[1]], "for TikTok")
    assert guardrails.hook_gate([dict(flat[0], shot_size="MCU"), flat[1]]) is None                   # close
    assert guardrails.hook_gate([dict(flat[0], move="push in"), flat[1]]) is None                    # moving
    assert guardrails.hook_gate([dict(flat[0], prompt="Coffee splashes into a cup."), flat[1]]) is None   # a hook's words
    assert guardrails.hook_gate([dict(flat[0], shot_size="", move=""), flat[1]]) is None            # not said: not judged


def test_the_video_text_gate_finds_words_asked_of_a_video_model():
    assert "garbled" in guardrails.video_text_gate([shot("Sign", 'A wooden sign that reads "OPEN 24 HOURS" swings.')])
    assert "garbled" in guardrails.video_text_gate([shot("Title", 'The words "SUMMER SALE" in big neon letters.')])
    assert guardrails.video_text_gate([shot("Talk", 'Maya says: "We are late."')]) is None             # spoken, not drawn
    assert "garbled" in guardrails.video_text_gate([shot("Shop", 'A shop sign that says "OPEN" flickers.')])
    assert guardrails.video_text_gate([dict(shot("Poster", 'A sign that reads "CHAI 10".'), workflow="image/flux2")]) is None


def test_the_quality_gates_are_one_hint_once_and_never_a_block(client, monkeypatch):
    register(client)
    flat = [dict(STEP, name=n, shot_size="WS", move="static", prompt="A quiet street.") for n in ("A", "B", "C")]
    seen = hosted(monkeypatch, client, {"tool": "finish", "reply": "Three.", "steps": flat})
    plan = client.post("/api/agent/plan", json={"instruction": "three shots of a street for reels"}).json()
    notes = told(seen)[-1]
    assert "every shot is WS" in notes and "first one or two seconds" in notes
    assert len(seen) == 2 and len(plan["steps"]) == 3   # the same plan again: the model decided to keep it

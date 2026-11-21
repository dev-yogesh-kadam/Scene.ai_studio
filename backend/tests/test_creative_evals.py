"""Measuring taste (docs/evals.md, docs/creative-rubric.md): the creative cases, the live-only judge and its
thresholds, the calibration tool (with a fake person and a fake judge), the rubric's marks in Langfuse, and the
harvest of candidates, which never reach the live sets on their own."""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals import calibrate, creative, harvest, run  # noqa: E402
from scene import agent  # noqa: E402

MARKS = {"idea": 4, "hook": 3, "craft": 4, "fit": 5, "prompt_quality": 3, "honesty": 4}


def test_the_creative_set_is_twenty_cases_with_its_traps_and_languages():
    cases = [c for c in run.load() if c["_file"] == "creative.json"]
    assert len(cases) == 20 and all("creative" in c["tags"] and c["expect"].get("creative") for c in cases)
    assert {c["lang"] for c in cases} == {"en", "hi", "es"}
    tags = {t for c in cases for t in c["tags"]}
    assert {"open-brief", "ad", "reels", "drama", "trap", "big-job", "small", "language"} <= tags
    traps = {c["id"] for c in cases if "trap" in c["tags"]}
    assert {"en-trap-text-in-video", "en-trap-celebrity", "en-creative-twenty-shot-trap"} <= traps


def test_the_judge_runs_in_live_mode_only_and_the_structure_in_replay():
    assert "creative" in run.LIVE_ONLY and "creative" not in run.REPLAY_ONLY and "examples" in run.REPLAY_ONLY
    plan = {"steps": [], "questions": [{"text": "Who?", "options": ["a", "b"]}], "concept": ""}
    replay = run.check({"creative": True, "brief_asked": True, "concept": False},
                       {"plan": plan, "live": False, "status": 200, "played": None})
    assert [name for name, _, _ in replay] == ["brief_asked", "concept"] and all(ok for _, ok, _ in replay)

    class Portal:
        def __init__(self, marks):
            self.marks = marks

        def call(self, function, brain, case, plan):
            return {"marks": self.marks, "why": "Strong hook.", "model": "claude/opus"}

    class Client:
        def __init__(self, marks):
            self.portal = Portal(marks)
            self.app = type("App", (), {"state": type("State", (), {"agent": None})()})()

    good = {"plan": {"steps": []}, "live": True, "status": 200, "client": Client(MARKS), "case": {}}
    assert run.check({"creative": True}, good) == [("creative", True, "")]
    weak = dict(good, client=Client(dict(MARKS, hook=2)))
    (name, ok, said), = run.check({"creative": True}, weak)
    assert not ok and "hook 2 < 3" in said
    strict = run.check({"creative": {"fit": 5, "idea": 5}}, good)
    assert not strict[0][1] and "idea 4 < 5" in strict[0][2]


def test_the_judge_reads_the_whole_plan_and_needs_every_mark():
    case = {"ask": {"instruction": "an ad for my cafe", "direction": "Brief: locals"}}
    plan = {"reply": "Three shots.", "concept": "Warm refuge.", "steps": [{"name": "Rain", "kind": "video", "settings": {
        "workflow": "video/@seedance_2_5", "prompt": "A woman runs through rain."}}],
            "questions": [{"text": "Tone?", "options": ["Warm", "Funny"], "details": ["cosy", ""]}]}
    text = creative.plan_text(case, plan)
    for words in ("an ad for my cafe", "Brief: locals", "Warm refuge.", "A woman runs through rain.", "Tone? Options: Warm; Funny"):
        assert words in text

    class Brain:
        def __init__(self, answer):
            self.answer = answer

        async def stronger(self, model=None):
            return "claude/opus"

        async def chat(self, messages, shape, model=None, purpose=""):
            assert model == "claude/opus" and purpose == "creative judge" and "creative rubric" in messages[0]["content"]
            return dict(self.answer, _model=model)
    found = asyncio.run(creative.judge(Brain(dict(MARKS, why="ok")), case, plan))
    assert found["marks"] == MARKS and found["model"] == "claude/opus"
    try:
        asyncio.run(creative.judge(Brain({"idea": 4, "why": "x"}), case, plan))
        assert False, "a judge that left marks out passed"
    except agent.AgentError as error:
        assert "hook" in str(error)
    assert creative.below(MARKS, True) == [] and creative.thresholds({"fit": 5})["fit"] == 5


def test_calibrate_asks_the_person_for_each_mark_saves_them_and_says_how_far_the_judge_is(tmp_path):
    said = iter(["5", "", "4", "x", "4", "3", "2", "4"])   # Enter skips hook; "x" is asked again
    lines = []
    path = tmp_path / "calibration.json"
    calibrate.main(["--case", "en-creative-small-single-shot"], ask=lambda prompt: next(said), out=lines.append,
                   judge=lambda case, plan: {"marks": MARKS, "why": "Clean.", "model": "claude/opus"}, path=path)
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert len(kept) == 1 and kept[0]["case"] == "en-creative-small-single-shot" and kept[0]["mode"] == "replay"
    assert kept[0]["human"] == {"idea": 5, "craft": 4, "fit": 4, "prompt_quality": 3, "honesty": 2}
    assert any("Sunset run" in line for line in lines)                       # the plan was shown
    assert any("a whole number from 1 to 5" in line for line in lines)
    apart = calibrate.distance(kept)
    assert apart["idea"] == {"n": 1, "mean_distance": 1.0, "mean_lean": -1.0} and apart["hook"]["n"] == 0
    assert apart["honesty"]["mean_lean"] == 2.0
    assert any("leaning" in line for line in lines)


def test_the_grade_gives_the_rubrics_marks_and_langfuse_gets_them_as_creative_scores(client, monkeypatch):
    from scene.api import workspace
    brain = client.app.state.agent

    async def fake_chat(messages, shape, **kwargs):
        assert set(agent.RUBRIC_MARKS) <= set(shape["required"]) and "creative rubric" in messages[0]["content"]
        return {"skill": 1, "clear": 0.5, "steps": 1, **MARKS, "why": "Fine."}
    monkeypatch.setattr(brain, "chat", fake_chat)
    sent = []
    fake = type("Langfuse", (), {"score": lambda self, run, name, value, comment="": sent.append((name, value))})()
    monkeypatch.setattr(client.app.state.traces, "langfuse", fake, raising=False)
    asyncio.run(workspace._grade(client.app.state, "an ad", [], "ok", [], None, None))
    assert sent[0][0] == "claude-grade" and dict(sent[1:]) == {"creative-" + k.replace("_", "-"): v for k, v in MARKS.items()}
    assert agent.rubric_marks({"idea": 9, "hook": 0, "craft": True, "fit": 2.6}) == {"idea": 5, "hook": 1, "fit": 3}


def test_harvest_writes_candidates_from_the_studios_tables_and_never_into_the_live_sets(client, tmp_path):
    from test_api import register
    me = register(client)
    db = client.app.state.db
    now = time.time()
    session = db.run("INSERT INTO claude_sessions (ref, user_id, project_id, run, agent, model, context_window, status, started, active) "
                     "VALUES ('SES1', ?, NULL, 'main', 'AGT1', 'sonnet', 1000000, 'open', ?, ?)", (me["id"], now - 100, now - 100))
    db.run("INSERT INTO claude_events (session_id, at, kind, text, data) VALUES (?, ?, 'user', 'an ad for my cafe', '')", (session, now - 60))
    steps = [{"name": "Rain run", "kind": "video", "settings": {"prompt": "A woman runs through the rain.", "orientation": "portrait"}}]
    for job, rating in (("j-good", 1), ("j-bad", -1)):
        db.run("INSERT INTO jobs (id, user_id, name, workflow, kind, settings, status, created) VALUES (?, ?, 'x', 'video/x', 'video', '{}', 'done', ?)",
               (job, me["id"], now))
        db.run("INSERT INTO generations (user_id, job_id, workflow, kind, name, filename, summary, settings, context, created, rating) "
               "VALUES (?, ?, 'video/x', 'video', 'x', 'x.mp4', '', '{}', '{}', ?, ?)", (me["id"], job, now, rating))
        db.run("INSERT INTO agent_plans (user_id, steps, progress, state, created, approved) VALUES (?, ?, ?, 'done', ?, ?)",
               (me["id"], json.dumps(steps), json.dumps([{"job": job}]), now - 30, now - 20))
    turns = harvest.local_turns(db, days=1)
    assert sorted(t["verdict"] for t in turns) == ["down", "up"] and all(t["brief"] == "an ad for my cafe" for t in turns)
    made = harvest.write(turns, tmp_path / "gold", tmp_path / "cases")
    gold = json.loads(made["gold"][0].read_text(encoding="utf-8"))
    assert gold["status"] == "draft" and gold["brief"] == "an ad for my cafe" and gold["context"]["platform"] == "portrait"
    assert gold["plan_outline"] == ["1. Rain run · video: A woman runs through the rain."]
    case = json.loads(made["cases"][0].read_text(encoding="utf-8"))
    assert case["expect"] == {"creative": True} and case["ask"]["instruction"] == "an ad for my cafe" and case["lang"] == "en"
    assert harvest.write(turns, tmp_path / "gold", tmp_path / "cases") == {"gold": [], "cases": []}   # never twice
    # the live sets read only their own folder: a candidate is never a gold example or a case on its own
    from scene import craft_library
    assert harvest.GOLD_CANDIDATES.parent == craft_library.GOLD and harvest.CASE_CANDIDATES.parent == run.CASES
    assert not any(e["id"].startswith("cand-") for e in craft_library.examples())
    assert not any("candidate" in c["tags"] for c in run.load())


def test_harvest_reads_the_studios_scores_from_langfuse_and_a_bad_one_wins():
    scored = {"user-thumb": [{"traceId": "t1", "value": 1}, {"traceId": "t2", "value": 0}],
              "approved": [{"traceId": "t1", "value": 1}, {"traceId": "t3", "value": 1}],
              "retaken": [{"traceId": "t3", "value": 1}], "review": [{"traceId": "t4", "value": 0.5}, {"traceId": "t5", "value": 0}],
              "user-feedback": []}

    def answer(request):
        if request.url.path == "/api/public/v2/scores":
            return httpx.Response(200, json={"data": scored[request.url.params["name"]]})
        found = {"t1": {"input": {"instruction": "a reel for my bakery"}, "output": {"reply": "Four.", "steps": [{"name": "Crack"}]}},
                 "t2": {"input": "मेरी चाय की दुकान के लिए एक रील", "output": {}},
                 "t3": {"input": "an ad for my gym"}, "t5": {"input": "a horror scene"}}
        return httpx.Response(200, json=found[request.url.path.rsplit("/", 1)[-1]])
    client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    turns = {t["brief"][:12]: t["verdict"] for t in asyncio.run(harvest.langfuse_turns(("http://lf.test", "Basic x"), client=client))}
    # liked and approved: up; disliked: down; approved then retaken: retaken (bad wins); a minor review says nothing
    assert turns == {"a reel for m": "up", "मेरी चाय की ": "down", "an ad for my": "retaken", "a horror sce": "major"}
    assert harvest.case_candidate({"id": "x", "ref": "r", "source": "langfuse", "brief": "मेरी चाय", "steps": [], "at": ""})["lang"] == "hi"


# ---------------------------------------------------------------- real feedback reaches Langfuse

def langfuse_on(client):
    from test_langfuse import _langfuse_row
    _langfuse_row(client.app.state.db)
    client.app.state.traces.langfuse.scores.clear()
    return client.app.state.traces.langfuse


def made_in_a_turn(client, user_id, run="abc123"):
    """A library item whose job was planned in the turn `run` (what item_score finds the trace by)."""
    from test_api import JOB
    job = client.post("/api/jobs", data={"settings": json.dumps(dict(JOB, turn={"run": run, "name": "Agent turn"}))}).json()["id"]
    return client.app.state.db.run("INSERT INTO generations (user_id, job_id, workflow, kind, name, filename, settings, context, created) "
                                   "VALUES (?, ?, 'video/@seedance_2_5', 'video', 'Pour', 'p.mp4', '{}', '{}', ?)", (user_id, job, time.time()))


def scores_of(sender, name):
    return [entry["body"] for entry in sender.scores if entry["body"]["name"] == name]


def test_a_thumb_is_a_user_thumb_score_and_turned_over_it_replaces_the_old_one(client):
    from scene import langfuse_trace
    from test_api import register
    me = register(client)
    sender = langfuse_on(client)
    item = made_in_a_turn(client, me["id"])
    client.put("/api/library/%d" % item, json={"rating": 1})
    client.put("/api/library/%d" % item, json={"rating": -1})
    thumbs = scores_of(sender, "user-thumb")
    assert [t["value"] for t in thumbs] == [1, 0] and {t["id"] for t in thumbs} == {"rating-%d" % item}   # one key: replaced
    assert thumbs[0]["traceId"] == langfuse_trace.trace_id("abc123")


def test_a_review_verdict_is_a_review_score_fine_minor_or_major(client, monkeypatch):
    from scene import review
    from test_api import register
    me = register(client)
    sender = langfuse_on(client)
    item = made_in_a_turn(client, me["id"])
    row = client.app.state.db.one("SELECT * FROM generations WHERE id = ?", (item,))
    folder = client.app.state.outputs.folder(me["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "p.mp4").write_bytes(b"x")

    async def frames(path, kind):
        return [("the result", "jpeg")]
    monkeypatch.setattr(review, "result_frames", frames)
    for level, value in (("fine", 1), ("minor", 0.5), ("major", 0)):
        async def checked(pictures, labels, prompt, kind="video", model=None, level=level):
            return {"checks": [{"check": "what", "level": level, "note": "n"}], "problem": "", "fix": {"prompt": "p", "why": "w"}}
        monkeypatch.setattr(client.app.state.agent, "review", checked)
        asyncio.run(review.review_item(client.app.state, me["id"], row, "a pour"))
    assert [s["value"] for s in scores_of(sender, "review")] == [1, 0.5, 0]
    assert {s["id"] for s in scores_of(sender, "review")} == {"review-%d" % item}


def test_a_retake_is_a_retaken_score_once_and_a_first_take_is_none(client):
    from test_api import JOB, register
    me = register(client)
    sender = langfuse_on(client)
    client.app.state.jobs.langfuse = sender
    item = made_in_a_turn(client, me["id"])
    assert scores_of(sender, "retaken") == []                       # a first take is no retake
    client.post("/api/jobs", data={"settings": json.dumps(dict(JOB, parent=item, shot={"id": "s1", "take": 2}))})
    retaken = scores_of(sender, "retaken")
    assert len(retaken) == 1 and retaken[0]["value"] == 1 and retaken[0]["id"] == "retaken-%d" % item


def test_an_approved_plan_is_an_approved_score_on_the_turn_it_was_planned_in(client, monkeypatch):
    from scene import langfuse_trace
    from test_agent_conversation import STEP
    from test_agent_shots import hosted
    from test_api import register
    register(client)
    sender = langfuse_on(client)
    hosted(monkeypatch, client, {"tool": "finish", "reply": "One shot.", "steps": [STEP]})
    step = client.post("/api/agent/plan", json={"instruction": "a dog in a park"}).json()["steps"][0]
    made = client.post("/api/agent/plans", json={"steps": [step]}).json()
    assert client.post("/api/agent/plans/{}/approve".format(made["id"])).status_code == 200
    approved = scores_of(sender, "approved")
    assert len(approved) == 1 and approved[0]["value"] == 1 and approved[0]["id"] == "plan-approved-{}".format(made["id"])
    assert approved[0]["traceId"] == langfuse_trace.trace_id(step["settings"]["turn"]["run"])

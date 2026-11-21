"""Langfuse: set in the console's Servers with its two keys (kept encrypted), it is sent every call of the agent's
models as an OpenTelemetry span, in the background; with none set, or one that does not answer, the calls are let go."""

import asyncio
import json
import time

import httpx

from scene import langfuse_trace, traces, vault
from test_api import JOB, console, register


def _attributes(span):
    return {a["key"]: a["value"]["stringValue"] for a in span["attributes"]}


def test_langfuse_is_set_in_the_console_with_its_keys_kept_secret(client):
    register(client)
    desk = console(client)
    desk.post("/api/admin/endpoints", json={"kind": "langfuse", "name": "Tracing", "url": "127.0.0.1:3000", "api_key": "pk-lf-1:sk-lf-2"})
    row = client.app.state.db.one("SELECT * FROM endpoints WHERE kind = 'langfuse'")
    assert row["url"] == "http://127.0.0.1:3000" and row["api_key"].startswith(vault.MARK)
    assert vault.reveal(row["api_key"]) == "pk-lf-1:sk-lf-2"
    shown = [e for e in desk.get("/api/admin/endpoints").json()["endpoints"] if e["kind"] == "langfuse"]
    assert shown[0]["has_key"] and "api_key" not in shown[0]
    desk.put("/api/admin/endpoints/%d" % row["id"], json={"name": "Langfuse", "api_key": ""})   # empty: the keys are kept
    assert vault.reveal(client.app.state.db.one("SELECT api_key FROM endpoints WHERE id = ?", (row["id"],))["api_key"]) == "pk-lf-1:sk-lf-2"
    from scene import endpoints
    endpoints.seed(client.app.state.db, client.app.state.settings)   # kept at the next start
    assert client.app.state.db.one("SELECT 1 FROM endpoints WHERE kind = 'langfuse'")
    assert client.app.state.traces.langfuse.target() == ("http://127.0.0.1:3000", "Basic cGstbGYtMTpzay1sZi0y")


def test_each_call_is_sent_as_a_span_of_its_turn(client):
    db = client.app.state.db
    sender = langfuse_trace.Sender(db)
    recorder = traces.Recorder(db, client.app.state.storage_dir / "calls_test")
    recorder.langfuse = sender
    run, session = traces.RUN.set("abc123"), traces.SESSION.set("1:main:4")
    try:
        usage = {"prompt": 1000, "cached": 600, "written": 300, "answer": 50}
        recorder.record("plan", "claude/sonnet", "claude/sonnet", time.time() - 2,
                        [{"role": "user", "content": "a red car", "images": ["xx", "yy"]}], {}, content={"reply": "ok"}, usage=usage, tool="make_image")
        recorder.record("caption", None, "claude/haiku", time.time() - 1, [{"role": "user", "content": "x"}], {}, error="Claude is busy")
    finally:
        traces.RUN.reset(run), traces.SESSION.reset(session)
    first, second = sender.waiting
    assert first["traceId"] == second["traceId"] and len(first["traceId"]) == 32   # one turn, one trace
    seen = _attributes(first)
    assert seen["langfuse.observation.type"] == "generation" and seen["session.id"] == "1:main:4"
    assert json.loads(seen["langfuse.observation.input"])[0]["images"] == 2   # how many pictures, not the pictures
    assert json.loads(seen["langfuse.observation.usage_details"]) == {
        "input": 100, "output": 50, "cache_read_input_tokens": 600, "cache_creation_input_tokens": 300}
    dollars = json.loads(seen["langfuse.observation.cost_details"])   # Sonnet 5.5: 2 / 10 / 0.20 / 4 per million
    assert dollars == {"input": 0.0002, "output": 0.0005, "cache_read_input_tokens": 0.00012, "cache_creation_input_tokens": 0.0012,
                       "total": 0.00202}
    assert seen["langfuse.observation.metadata.tool"] == "make_image"
    failed = _attributes(second)
    assert failed["langfuse.observation.level"] == "ERROR" and second["status"]["code"] == 2


def test_the_calls_go_in_the_background_and_wait_while_langfuse_is_down(client):
    db = client.app.state.db
    sender = langfuse_trace.Sender(db)
    sender.add("plan", "claude/sonnet", "claude/sonnet", 1.0, 2.0, [])
    assert asyncio.run(_send(sender, lambda request: httpx.Response(200))) == 0 and not sender.waiting   # none set: let go

    db.run("INSERT INTO endpoints (kind, name, url, api_key, models, active, created) VALUES ('langfuse', 'L', 'http://lf', ?, '', 1, ?)",
           (vault.seal("pk:sk"), time.time()))
    got = []

    def answer(request):
        got.append(request)
        return httpx.Response(200 if len(got) > 1 else 503)

    for _ in range(3):
        sender.add("plan", "claude/sonnet", "claude/sonnet", 1.0, 2.0, [])
    try:
        asyncio.run(_send(sender, answer))
    except httpx.HTTPStatusError:
        pass
    assert len(sender.waiting) == 3   # not taken: kept for the next time
    assert asyncio.run(_send(sender, answer)) == 3 and not sender.waiting
    sent = got[-1]
    assert sent.url.path == "/api/public/otel/v1/traces" and sent.headers["Authorization"] == "Basic cGs6c2s="
    assert len(json.loads(sent.content)["resourceSpans"][0]["scopeSpans"][0]["spans"]) == 3


async def _send(sender, answer):
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        return await sender.send(http)


def _langfuse_row(db, url="http://lf"):
    db.run("INSERT INTO endpoints (kind, name, url, api_key, models, active, created) VALUES ('langfuse', 'L', ?, ?, '', 1, ?)",
           (url, vault.seal("pk:sk"), time.time()))


def test_a_turn_is_one_named_trace_with_its_skills_and_what_its_tokens_cost_in_credits(client):
    db, credits = client.app.state.db, client.app.state.credits
    sender = langfuse_trace.Sender(db, credits)
    turn = {"name": "Agent turn", "tags": ["product-ad"], "metadata": {"project": 4, "project_ref": "PRJabc", "skills": ["product-ad"],
                                                                         "film_run": False, "run": None}}
    usage = {"prompt": 1000, "cached": 600, "written": 300, "answer": 50}
    sender.add("plan", "claude/sonnet", "claude/sonnet", 1.0, 2.0, [], {"reply": "ok"}, usage, run="abc123", turn=turn)
    sender.add("describe", "claude/haiku", "claude/haiku", 1.0, 2.0, [], run="abc123")   # not in a turn: named by its purpose
    first, second = (_attributes(s) for s in sender.waiting)
    assert sender.waiting[0]["traceId"] == langfuse_trace.trace_id("abc123") == sender.waiting[1]["traceId"]
    assert first["langfuse.trace.name"] == "Agent turn" and json.loads(first["langfuse.trace.tags"]) == ["product-ad"]
    assert first["langfuse.trace.metadata.project_ref"] == "PRJabc" and json.loads(first["langfuse.trace.metadata.skills"]) == ["product-ad"]
    assert "langfuse.trace.metadata.run" not in first   # nothing is sent for what is not known
    assert second["langfuse.trace.name"] == "describe"
    # $0.00202 at 88 rupees a dollar, a credit worth 0.10 rupees: 1.78 credits, so 2
    assert first["langfuse.observation.metadata.credits"] == str(credits.token_cost("claude/sonnet", usage)) == "2"
    assert first["langfuse.observation.metadata.rupees"] == "0.2" and first["langfuse.observation.metadata.inr_per_usd"] == "88.0"


def test_long_words_are_cut_and_with_words_off_only_numbers_go(client):
    db = client.app.state.db
    sender = langfuse_trace.Sender(db)
    long = "x" * (langfuse_trace.LONGEST + 500)
    sender.add("plan", "claude/sonnet", "claude/sonnet", 1.0, 2.0, [{"role": "system", "content": long}, {"role": "user", "content": "hi"}],
               {"reply": long})
    seen = _attributes(sender.waiting[0])
    sent = json.loads(seen["langfuse.observation.input"])
    assert len(sent[0]["content"]) < langfuse_trace.LONGEST + 100 and sent[0]["content"].endswith("500 more characters not sent to Langfuse]")
    assert sent[1]["content"] == "hi" and len(seen["langfuse.observation.output"]) < langfuse_trace.LONGEST + 100

    db.set_setting("langfuse_words", "0")
    sender.add("plan", "claude/sonnet", "claude/sonnet", 1.0, 2.0, [{"role": "user", "content": "a secret plan"}], {"reply": "secret"},
               {"prompt": 10, "answer": 5}, run="r1")
    sender.score("r1", "claude-grade", 0.5, "the reply was vague")
    quiet = _attributes(sender.waiting[1])
    assert "langfuse.observation.input" not in quiet and "langfuse.observation.output" not in quiet
    assert json.loads(quiet["langfuse.observation.usage_details"])["output"] == 5 and quiet["gen_ai.request.model"] == "claude/sonnet"
    assert "secret" not in json.dumps(sender.waiting[1]) and "comment" not in sender.scores[0]["body"]


def test_scores_go_to_the_ingestion_route_on_the_turns_trace(client):
    db = client.app.state.db
    sender = langfuse_trace.Sender(db)
    sender.score("abc123", "user-feedback", 1, "liked", key="rating-7")
    sender.score("abc123", "user-feedback", 0, key="rating-7")   # turned over: the same key, so Langfuse keeps the last
    _langfuse_row(db)
    got = []

    def answer(request):
        got.append(request)
        return httpx.Response(207, json={"successes": [{"id": "1", "status": 201}], "errors": []})

    assert asyncio.run(_send(sender, answer)) == 2 and not sender.scores
    assert got[0].url.path == "/api/public/ingestion"
    batch = json.loads(got[0].content)["batch"]
    assert [e["type"] for e in batch] == ["score-create", "score-create"]
    assert batch[0]["body"] == {"id": "rating-7", "traceId": langfuse_trace.trace_id("abc123"), "name": "user-feedback", "value": 1,
                                "dataType": "NUMERIC", "comment": "liked"}


def test_renders_join_the_trace_of_the_turn_that_planned_them_and_others_have_their_own(client, monkeypatch):
    from test_agent_decisions import SHOT
    register(client)
    state = client.app.state
    state.jobs.pause(True)   # nothing renders while the test looks
    seen = {}

    async def fake_ask(system, message, workflow_ids, history=(), model=None):
        seen.update(run=traces.RUN.get(), turn=traces.TURN.get())
        return {"reply": "Planned.", "steps": [dict(SHOT, name="Pour", prompt="Coffee pours into a cup.", duration=5)]}
    monkeypatch.setattr(state.agent, "ask", fake_ask)
    step = client.post("/api/agent/plan", json={"instruction": "a coffee ad"}).json()["steps"][0]
    assert seen["turn"]["name"] == "Agent turn" and step["settings"]["turn"] == {"run": seen["run"], "name": "Agent turn"}

    # approved later, in another request: the job keeps the turn it was planned in
    planned = client.post("/api/jobs", data={"settings": json.dumps(step["settings"])}).json()["id"]
    alone = client.post("/api/jobs", data={"settings": json.dumps(JOB)}).json()["id"]
    sender = langfuse_trace.Sender(state.db)
    state.jobs.langfuse = sender
    for job_id in (planned, alone):
        job = state.db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        job.update(settings=json.loads(job["settings"]), started=job["created"] + 4, server="Test provider", server_url="http://fake-v1")
        state.jobs._traced(job, "done", None)
    ours, theirs = sender.waiting
    assert ours["traceId"] == langfuse_trace.trace_id(seen["run"]) and theirs["traceId"] != ours["traceId"]
    first, second = _attributes(ours), _attributes(theirs)
    assert first["langfuse.observation.type"] == "span" and first["langfuse.trace.name"] == "Agent turn"
    assert second["langfuse.trace.name"] == "Render"
    assert first["langfuse.observation.metadata.workflow"] == "video/@seedance_2_5" and first["langfuse.observation.metadata.server"] == "Test provider"
    assert first["langfuse.observation.metadata.queue_seconds"] == "4.0" and int(first["langfuse.observation.metadata.credits"]) > 0

    # a thumb on what it made is a score on that turn's trace
    item = state.db.run("INSERT INTO generations (user_id, job_id, workflow, kind, name, filename, settings, context, created) "
                        "VALUES (1, ?, 'video/@seedance_2_5', 'video', 'Pour', 'p.mp4', '{}', '{}', ?)", (planned, time.time()))
    state.traces.langfuse.scores.clear()
    _langfuse_row(state.db)
    assert client.put("/api/library/%d" % item, json={"rating": -1}).status_code == 200
    score = state.traces.langfuse.scores[0]["body"]
    assert score["traceId"] == ours["traceId"] and score["name"] == "user-thumb" and score["value"] == 0


def test_grading_is_off_unless_an_admin_sets_a_share(client):
    from scene.api import workspace
    register(client)
    state = client.app.state
    assert not workspace._grading(state)   # off by default
    desk = console(client)
    shown = desk.get("/api/admin/settings").json()
    assert shown["langfuse_grade_share"] == 0 and shown["langfuse_words"] is True
    desk.put("/api/admin/settings", json={"langfuse_grade_share": 100, "langfuse_words": False})
    assert state.db.setting("langfuse_words") == "0"
    assert not workspace._grading(state)   # every turn, but there is no Langfuse to send it to
    _langfuse_row(state.db)
    assert workspace._grading(state)

    async def fake_chat(messages, answer_format, model=None, purpose="plan", **kwargs):
        assert purpose == "grade" and "Coffee" in messages[1]["content"]
        return {"skill": 1, "clear": 0.5, "steps": "0.9", "why": "The reply  is short."}
    state.agent.chat = fake_chat
    found = asyncio.run(state.agent.grade("a coffee ad", [{"title": "Ad", "text": "Ask first."}], "Here.", [{"name": "Coffee", "prompt": "pour"}]))
    assert found["score"] == 0.8 and found["why"].startswith("The reply is short.")


def test_a_call_is_kept_in_a_dataset_and_says_plainly_when_langfuse_is_not_there(client):
    register(client)
    state = client.app.state
    desk = console(client)
    call = state.traces.record("plan", "claude/sonnet", "claude/sonnet", time.time(), [{"role": "user", "content": "a red car"}], {},
                               content={"reply": "ok"})
    refused = desk.post("/api/admin/agent/calls/%d/dataset" % call, json={"dataset": "plans"})
    assert refused.status_code == 400 and "No Langfuse" in refused.json()["detail"]
    _langfuse_row(state.db, "http://127.0.0.1:9")   # set, but nothing answers there
    down = desk.post("/api/admin/agent/calls/%d/dataset" % call, json={"dataset": "plans"})
    assert down.status_code == 502 and "did not answer" in down.json()["detail"]

    got = []

    def answer(request):
        got.append((request.method, request.url.raw_path.decode(), json.loads(request.content) if request.content else None))
        if request.method == "GET":
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(200, json={"id": "item-1"})

    async def keep():
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
            return await state.traces.langfuse.to_dataset("my plans", [{"role": "user", "content": "a red car"}], {"reply": "ok"},
                                                          "abc123", "good one", http=http)
    assert asyncio.run(keep())["id"] == "item-1"
    assert [g[:2] for g in got] == [("GET", "/api/public/v2/datasets/my%20plans"), ("POST", "/api/public/v2/datasets"),
                                    ("POST", "/api/public/dataset-items")]
    item = got[2][2]
    assert item["datasetName"] == "my plans" and item["sourceTraceId"] == langfuse_trace.trace_id("abc123") and item["expectedOutput"] == {"reply": "ok"}


def test_the_console_gets_where_a_run_opens_in_langfuse(client):
    register(client)
    state = client.app.state
    desk = console(client)
    run = traces.RUN.set("run42")
    try:
        state.traces.record("plan", "claude/sonnet", "claude/sonnet", time.time(), [{"role": "user", "content": "x"}], {})
    finally:
        traces.RUN.reset(run)
    report = desk.get("/api/admin/agent").json()
    assert report["langfuse"] is None   # none set: no link
    assert next(r for r in report["runs"] if r["run"] == "run42")["trace"] == langfuse_trace.trace_id("run42")

    async def link():
        projects = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"id": "studio"}]}))
        async with httpx.AsyncClient(transport=projects) as http:
            return await state.traces.langfuse.link(http)
    _langfuse_row(state.db)
    assert asyncio.run(link()) == {"url": "http://lf", "project": "studio"}
    assert desk.get("/api/admin/agent/runs/run42").json()["langfuse"] == {"url": "http://lf", "project": "studio"}   # kept a while


def test_a_user_is_shown_in_langfuse_by_their_email(client):
    register(client)
    db = client.app.state.db
    person = db.one("SELECT id, email FROM users ORDER BY id LIMIT 1")
    sender = langfuse_trace.Sender(db)
    sender.add("plan", "claude/sonnet", "claude/sonnet", 1.0, 2.0, [], user=person["id"])
    sender.add("plan", "claude/sonnet", "claude/sonnet", 1.0, 2.0, [], user=999999)   # no such user: the number
    first, second = (_attributes(span) for span in sender.waiting)
    assert first["user.id"] == person["email"] and first["langfuse.trace.metadata.user_id"] == str(person["id"])
    assert second["user.id"] == "999999"

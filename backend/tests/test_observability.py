"""Who keeps what of the agent's work (docs/observability.md): the sending to Langfuse never costs a user anything and
says how it goes, no key or password is sent, the prompts' versions go with each trace, saved turns go to datasets and
their evaluations to dataset runs, and with langfuse_owns_words on the words are kept in Langfuse only. No request
here reaches a real Langfuse: each one is answered by a fake (httpx.MockTransport)."""

import asyncio
import gzip
import json
import time

import httpx
import pytest

from scene import health, langfuse_trace, retention, traces, vault
from test_api import register
from test_schema import scratch  # noqa: F401  (a database of the test's own)


def _attributes(span):
    return {a["key"]: a["value"]["stringValue"] for a in span["attributes"]}


def _langfuse_row(db, url="http://lf"):
    db.run("INSERT INTO endpoints (kind, name, url, api_key, models, active, created) VALUES ('langfuse', 'L', ?, ?, '', 1, ?)",
           (url, vault.seal("pk:sk"), time.time()))


async def _send(sender, answer):
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        return await sender.send(http)


# ---------------------------------------------------------------- the sending

def test_spans_added_while_a_batch_is_on_its_way_are_not_lost_with_it(client, monkeypatch):
    """`add` runs on the database's threads while `send` waits on Langfuse: what came in meanwhile stays, whatever
    was let go past KEEP. (Before, the sent batch was taken off by position, so it took newer calls with it.)"""
    db = client.app.state.db
    monkeypatch.setattr(langfuse_trace, "KEEP", 5)
    _langfuse_row(db)
    sender = langfuse_trace.Sender(db)
    monkeypatch.setattr(sender, "words", lambda: True)   # the adds below run in the fake's answer, on the event loop
    for n in range(5):
        sender.add("plan", "claude/sonnet", None, 1.0, 2.0, [], run="old%d" % n)
    calls = []

    def answer(request):
        calls.append(request)
        if len(calls) == 1:   # while the first five are on their way, three more come and push three of them out
            for n in range(3):
                sender.add("plan", "claude/sonnet", None, 1.0, 2.0, [], run="new%d" % n)
            return httpx.Response(200)
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_send(sender, answer))
    assert [s["traceId"] for s in sender.waiting] == [langfuse_trace.trace_id("new%d" % n) for n in range(3)]
    state = sender.status()
    assert state["backlog"] == 3 and state["dropped"] == 3 and state["sent"] == 5 and state["down_since"]


def test_a_batch_langfuse_refuses_for_good_is_let_go_and_counted(client):
    db = client.app.state.db
    _langfuse_row(db)
    sender = langfuse_trace.Sender(db)
    sender.add("plan", "claude/sonnet", None, 1.0, 2.0, [])
    sender.score("r", "user-feedback", 1)
    assert asyncio.run(_send(sender, lambda request: httpx.Response(400, text="bad"))) == 0
    assert not sender.waiting and not sender.scores and sender.status()["refused"] == 2


def test_a_langfuse_that_is_down_is_a_problem_after_five_minutes_and_says_how_many_wait(client):
    state = client.app.state
    sender = state.traces.langfuse
    found = asyncio.run(health.langfuse(state))
    assert found["in_use"] is False and found["backlog"] == 0 and found["keep"] == langfuse_trace.KEEP
    _langfuse_row(state.db)
    sender.add("plan", "claude/sonnet", None, 1.0, 2.0, [])
    with pytest.raises(httpx.ConnectError):
        asyncio.run(_send(sender, lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused"))))
    found = asyncio.run(health.langfuse(state))
    assert found["in_use"] and found["url"] == "http://lf" and found["backlog"] == 1 and "ConnectError" in found["last_error"]
    assert not [p for p in asyncio.run(_problems(state)) if p["key"] == "langfuse"]   # a moment: not yet
    sender.health["down_since"] = time.time() - health.LANGFUSE_DOWN - 1
    sender.health["dropped"] = 7
    said = [p for p in asyncio.run(_problems(state)) if p["key"] == "langfuse"]
    assert said and said[0]["level"] == "warning" and said[0]["tab"] == "endpoints"
    assert "1 wait" in said[0]["text"] and "1,000 are kept" in said[0]["text"] and "7 lost" in said[0]["text"]
    assert asyncio.run(_send(sender, lambda request: httpx.Response(200))) == 1   # back: the problem is gone
    assert not [p for p in asyncio.run(_problems(state)) if p["key"] == "langfuse"] and sender.status()["last_sent"]


async def _problems(state):
    return await health.problems(state, model={"online": True, "detail": ""})


def test_with_words_off_no_word_of_the_user_goes_anywhere(client):
    db = client.app.state.db
    db.set_setting("langfuse_words", "0")
    sender = langfuse_trace.Sender(db)
    secret = "zebra-marmalade-plan"
    sender.add("plan", "claude/sonnet", None, 1.0, 2.0, [{"role": "user", "content": "make " + secret}], {"reply": secret},
               {"prompt": 10, "answer": 5}, error="Claude choked on " + secret, run="r1", call=12, answer_format={"x": secret})
    sender.span("render video/x", 1.0, 2.0, "r1", metadata={"workflow": "video/x"}, error="The provider: " + secret)
    sender.score("r1", "claude-grade", 0.5, "it said " + secret)
    sent = json.dumps([sender.waiting, sender.scores])
    assert secret not in sent
    first = _attributes(sender.waiting[0])
    assert first["langfuse.observation.level"] == "ERROR" and first["langfuse.observation.status_message"] == langfuse_trace.WORDS_OFF
    assert json.loads(first["langfuse.observation.usage_details"])["output"] == 5   # the numbers still go
    assert not sender.calls   # no words went, so none is let go here when Langfuse takes it


# ---------------------------------------------------------------- no key, token or password is sent

@pytest.mark.parametrize("said, kept", [
    ("my key is sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv_wxyz-0123", "my key is "),
    ("pk-lf-1234567890abcdef1234:sk-lf-abcdef1234567890abcd", ":"),
    ("token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "token "),
    ("aws AKIAIOSFODNN7EXAMPLE here", "aws "),
    ("hdr: Authorization: Bearer abcdefghijklmnop1234567890", "Bearer "),
    ("postgresql://someone:Sup3r-secret@db.example:5432/x", "postgresql://someone:"),
    ("password=hunter2-hunter2", "password="),
    ('{"api_key": "abc123def456ghi"}', '{"api_key": "'),
    ("SCENE_SECRET_KEY=Zm9vYmFyYmF6cXV4", "SCENE_SECRET_KEY="),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U", "jwt "),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----", ""),
    ("my password is correcthorse", "my password is "),
])
def test_keys_tokens_and_passwords_are_redacted(said, kept):
    out = langfuse_trace.redact(said)
    assert langfuse_trace.REDACTED in out and kept in out
    assert langfuse_trace.redact(json.dumps({"content": said})).count(langfuse_trace.REDACTED) >= 1   # inside JSON too


@pytest.mark.parametrize("said", [
    "write to anna@example.com about the claude-sonnet-4-5 shot", "max_tokens: 4096", '{"cache_read_input_tokens": 600}',
    "a 16:9 shot, 5 s, seed 123456789", "trace 3f2a9b0c1d2e3f4a5b6c7d8e9f001122", "the token of thanks", "https://example.com/a/b?c=d",
])
def test_ordinary_words_are_left_alone(said):
    assert langfuse_trace.redact(said) == said


def test_a_key_in_a_message_never_reaches_langfuse(client):
    sender = langfuse_trace.Sender(client.app.state.db)
    key = "sk-ant-api03-" + "Q" * 40
    sender.add("plan", "claude/sonnet", None, 1.0, 2.0, [{"role": "user", "content": "use my key " + key}], {"reply": "with " + key},
               error="refused " + key)
    sender.score("r", "claude-grade", 1, "it printed " + key)
    sent = json.dumps([sender.waiting, sender.scores])
    assert key not in sent and "use my key [redacted]" in sent


# ---------------------------------------------------------------- versions of the prompts

def test_each_call_carries_the_versions_of_the_system_prompt_and_its_skills(client):
    from scene import agent, skills
    skill = skills.load()[0]
    sender = langfuse_trace.Sender(client.app.state.db)
    turn = {"name": "Agent turn", "tags": [skill["id"]], "metadata": {"skills": [skill["id"], "no-such-skill"]}}
    sender.add("plan", "claude/sonnet", None, 1.0, 2.0, [], run="v1", turn=turn)
    sender.span("render x", 1.0, 2.0, "v1", turn={"name": "Agent turn"})
    seen, render = (_attributes(s) for s in sender.waiting)
    system = langfuse_trace.version_of(agent.SYSTEM)
    assert len(system) == 12 and seen["langfuse.version"] == system == seen["langfuse.trace.metadata.system_prompt"]
    assert json.loads(seen["langfuse.trace.metadata.skill_versions"]) == {skill["id"]: langfuse_trace.version_of(skill["text"])}
    assert "langfuse.version" not in render   # a render is not a prompt
    assert langfuse_trace.version_of("a") != langfuse_trace.version_of("b")


# ---------------------------------------------------------------- datasets and dataset runs

def _fake_langfuse(got, datasets=()):
    def answer(request):
        body = json.loads(request.content) if request.content else None
        path = request.url.raw_path.decode()
        got.append((request.method, path, body, request.headers.get("Authorization")))
        if request.method == "GET":
            return httpx.Response(200, json={"name": "x"}) if path.rsplit("/", 1)[-1] in datasets else httpx.Response(404)
        return httpx.Response(200, json={"id": (body or {}).get("id") or "made"})
    return answer


def test_a_dataset_run_keeps_each_result_as_a_trace_linked_to_its_item_with_its_scores(client):
    got = []
    key = "sk-ant-api03-" + "Z" * 30
    items = [{"key": "turn-1", "input": {"instruction": "a red car, key " + key}, "expected": {"steps": 1}, "source_run": "abc123"},
             {"key": "turn-2", "input": {"instruction": "a blue boat"}}]
    results = [{"key": "turn-2", "output": {"reply": "boat"}, "scores": {"follows_skill": 0.5}, "model": "claude/sonnet", "seconds": 2,
                "usage": {"prompt": 100, "answer": 10}},
               {"key": "turn-1", "output": {"reply": "car"}, "scores": {"follows_skill": 1, "verdict": "good"},
                "comments": {"follows_skill": "kept to it"}}]

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(_fake_langfuse(got))) as http:
            return await langfuse_trace.dataset_run("studio plans", items, results, "sonnet vs haiku", description="first",
                                                    target=("http://lf/", "pk-lf-1", "sk-lf-2"), http=http)
    done = asyncio.run(run())
    assert done["dataset"] == "studio plans" and done["run"] == "sonnet vs haiku" and done["scores"] == 3
    assert set(done["items"]) == {"turn-1", "turn-2"} and done["traces"]["turn-1"] == langfuse_trace.trace_id("eval:sonnet vs haiku:turn-1")
    paths = [(method, path) for method, path, _, _ in got]
    assert paths == [("GET", "/api/public/v2/datasets/studio%20plans"), ("POST", "/api/public/v2/datasets"),
                     ("POST", "/api/public/dataset-items"), ("POST", "/api/public/dataset-items"), ("POST", langfuse_trace.PATH),
                     ("POST", "/api/public/dataset-run-items"), ("POST", "/api/public/dataset-run-items"), ("POST", langfuse_trace.SCORES)]
    assert all(auth == langfuse_trace._auth("pk-lf-1", "sk-lf-2") for *_, auth in got)
    first_item = got[2][2]
    assert first_item["id"] == done["items"]["turn-1"] and first_item["sourceTraceId"] == langfuse_trace.trace_id("abc123")
    assert key not in json.dumps(got) and first_item["expectedOutput"] == {"steps": 1}
    spans = got[4][2]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    seen = _attributes(spans[0])
    assert seen["langfuse.trace.name"] == "Eval run" and json.loads(seen["langfuse.observation.output"]) == {"reply": "boat"}
    link = got[5][2]
    assert link == {"runName": "sonnet vs haiku", "runDescription": "first", "metadata": {}, "datasetItemId": done["items"]["turn-2"],
                    "traceId": spans[0]["traceId"], "observationId": spans[0]["spanId"]}
    scores = [e["body"] for e in got[7][2]["batch"]]
    assert {(s["name"], s["value"], s["dataType"]) for s in scores} == {
        ("follows_skill", 0.5, "NUMERIC"), ("follows_skill", 1, "NUMERIC"), ("verdict", "good", "CATEGORICAL")}
    assert any(s.get("comment") == "kept to it" for s in scores)

    # again: the same items (their ids are the same), the dataset already there
    got.clear()

    async def again():
        async with httpx.AsyncClient(transport=httpx.MockTransport(_fake_langfuse(got, {"studio%20plans"}))) as http:
            return await langfuse_trace.push_dataset("studio plans", items, target=("http://lf", "Basic x"), http=http)
    assert asyncio.run(again())["items"] == done["items"] and [m for m, *_ in got] == ["GET", "POST", "POST"]


def test_a_dataset_needs_a_langfuse_and_words_and_its_results_must_be_its_items(client, monkeypatch):
    db = client.app.state.db
    for name in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LookupError):
        asyncio.run(langfuse_trace.dataset_run("d", [{"key": "a", "input": "x"}], [], db=db))
    db.set_setting("langfuse_words", "0")
    with pytest.raises(PermissionError):
        asyncio.run(langfuse_trace.push_dataset("d", [{"key": "a", "input": "x"}], db=db))
    db.set_setting("langfuse_words", "1")
    with pytest.raises(ValueError):
        asyncio.run(langfuse_trace.dataset_run("d", [{"key": "a", "input": "x"}], [{"key": "b", "output": 1}], target=("http://lf", "B")))
    monkeypatch.setenv("LANGFUSE_HOST", "http://env-lf")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    assert langfuse_trace._target() == ("http://env-lf", "Basic cGs6c2s=")


# ---------------------------------------------------------------- langfuse_owns_words: one owner for the words

def _calls(client, tmp_path):
    db = client.app.state.db
    recorder = traces.Recorder(db, tmp_path / "calls")
    recorder.langfuse = sender = langfuse_trace.Sender(db)
    call = recorder.record("plan", "claude/sonnet", "claude/sonnet", time.time(), [{"role": "user", "content": "a red car"}],
                           {"type": "object"}, content={"reply": "ok"})
    return db, recorder, sender, call


def test_by_default_the_words_of_a_call_stay_here_after_langfuse_took_them(client, tmp_path):
    db, recorder, sender, call = _calls(client, tmp_path)
    _langfuse_row(db)
    assert sender.waiting[0]["spanId"] == langfuse_trace.call_span(call)
    assert "langfuse.observation.metadata.answer_format" not in _attributes(sender.waiting[0])
    assert asyncio.run(_send(sender, lambda request: httpx.Response(200))) == 1
    assert recorder.exchange(call)["answer"] == {"reply": "ok"}   # today's behaviour: a week here as well


def test_with_langfuse_owning_the_words_a_calls_file_goes_once_langfuse_has_it_and_is_read_back_from_there(client, tmp_path):
    db = client.app.state.db
    db.set_setting("langfuse_owns_words", "1")
    db, recorder, sender, call = _calls(client, tmp_path)
    seen = _attributes(sender.waiting[0])
    assert json.loads(seen["langfuse.observation.metadata.answer_format"]) == {"type": "object"}
    _langfuse_row(db)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_send(sender, lambda request: httpx.Response(503)))
    assert recorder.exchange(call) is not None   # not taken: the words stay here
    assert asyncio.run(_send(sender, lambda request: httpx.Response(200))) == 1
    assert recorder.exchange(call) is None and db.one("SELECT id FROM agent_calls WHERE id = ?", (call,))   # the row stays

    def observation(request):
        assert request.url.path == "/api/public/observations/" + langfuse_trace.call_span(call)
        return httpx.Response(200, json={"id": langfuse_trace.call_span(call), "input": seen["langfuse.observation.input"],
                                         "output": {"reply": "ok"}, "metadata": {"answer_format": '{"type": "object"}'}})

    async def read_back():
        async with httpx.AsyncClient(transport=httpx.MockTransport(observation)) as http:
            return await sender.exchange(call, http)
    words = asyncio.run(read_back())
    assert words["messages"] == [{"role": "user", "content": "a red car"}] and words["answer"] == {"reply": "ok"}
    assert words["format"] == {"type": "object"} and words["from"] == "langfuse"


def _session_with_events(db, now):
    user = db.run("INSERT INTO users (email, name, password_hash, created) VALUES ('ann@b.c', 'Ann', 'x', ?)", (now,))
    session = db.run("INSERT INTO claude_sessions (ref, user_id, project_id, run, started, active) VALUES ('SES9', ?, NULL, 'main', ?, ?)",
                     (user, now, now))
    old = now - 40 * 86400
    long = "the studio's whole message " * 40 + " key sk-ant-api03-" + "K" * 30
    ids = [db.run("INSERT INTO claude_events (session_id, at, kind, text, data) VALUES (?, ?, ?, ?, ?)", (session, at, kind, text, data))
           for at, kind, text, data in ((old, "prompt", long, ""), (old + 1, "tool_call", "make_image", json.dumps({"input": {"prompt": "a car"}})),
                                        (old + 2, "answer", "Done.", json.dumps({"steps": 2})), (now - 86400, "answer", "Yesterday.", ""))]
    return user, ids, long


def test_old_session_events_move_to_langfuse_only_when_it_owns_the_words_and_has_taken_them(client):
    db, now = client.app.state.db, time.time()
    sender = langfuse_trace.Sender(db)
    user, ids, long = _session_with_events(db, now)
    _langfuse_row(db)
    assert retention.move_events(db, sender, now) == 0   # off by default: nothing is sent or changed
    assert db.one("SELECT text FROM claude_events WHERE id = ?", (ids[0],))["text"] == long

    db.set_setting("langfuse_owns_words", "1")
    down = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        retention.move_events(db, sender, now, http=down)
    assert db.one("SELECT COUNT(*) n FROM claude_events WHERE moved IS NOT NULL")["n"] == 0   # not taken: all stay whole

    got = []
    up = httpx.Client(transport=httpx.MockTransport(lambda request: got.append(json.loads(request.content)) or httpx.Response(200)))
    assert retention.move_events(db, sender, now, http=up) == 3
    spans = got[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    seen = _attributes(spans[0])
    assert seen["session.id"] == "{}:main:0".format(user) and seen["user.id"] == "ann@b.c" and seen["langfuse.trace.name"] == "Claude session"
    assert seen["langfuse.observation.input"].startswith("the studio's whole message") and "sk-ant-" not in json.dumps(got)
    assert spans[0]["spanId"] == langfuse_trace.event_span(ids[0])
    rows = {r["id"]: r for r in db.all("SELECT id, text, data, moved FROM claude_events")}
    first = rows[ids[0]]
    assert first["moved"] and len(first["text"]) < len(long) and first["text"].endswith("more characters in Langfuse]")
    assert json.loads(first["data"])["langfuse"] == {"trace": spans[0]["traceId"], "observation": spans[0]["spanId"]}
    assert "input" not in json.loads(rows[ids[1]]["data"]) and json.loads(rows[ids[2]]["data"])["steps"] == 2   # numbers stay
    assert rows[ids[3]]["text"] == "Yesterday." and rows[ids[3]]["moved"] is None   # within 30 days: whole
    assert retention.move_events(db, sender, now, http=up) == 0   # each once


# ---------------------------------------------------------------- what is kept, and archived once

def test_with_retention_set_the_calls_are_left_to_it_so_none_is_deleted_unarchived(client):
    register(client)
    recorder = client.app.state.traces
    old = recorder.record("caption", "m", None, time.time() - 40 * 86400, [{"role": "user", "content": "x"}], "json", content={})
    recorder.prune(retention_days=90)
    assert client.app.state.db.one("SELECT id FROM agent_calls WHERE id = ?", (old,))
    recorder.prune()   # retention off: a month, as always
    assert not client.app.state.db.one("SELECT id FROM agent_calls WHERE id = ?", (old,))


def test_rows_archived_twice_by_a_crash_are_read_once(database, tmp_path, monkeypatch):
    db = database
    user = db.run("INSERT INTO users (email, name, password_hash, created) VALUES ('a@b.c', 'A', 'x', ?)", (time.time(),))
    old = time.time() - 120 * 86400
    db.run("INSERT INTO agent_calls (run, user_id, started) VALUES ('r', ?, ?)", (user, old))
    real = db.run

    def crash(sql, params=()):
        if sql.startswith("DELETE FROM agent_calls"):
            raise RuntimeError("the power went")
        return real(sql, params)
    monkeypatch.setattr(db, "run", crash)
    with pytest.raises(RuntimeError):
        retention.archive(db, tmp_path, days=90)
    monkeypatch.setattr(db, "run", real)
    assert retention.archive(db, tmp_path, days=90)["agent_calls"] == 1
    path = tmp_path / "archive" / "agent_calls_{}.jsonl.gz".format(time.strftime("%Y-%m", time.gmtime(old)))
    assert len([l for l in gzip.open(path, "rt", encoding="utf-8") if l.strip()]) == 2   # written twice
    assert len(retention.read(path)) == 1                                              # read once


def test_the_moved_column_of_0013_comes_and_goes_with_it(scratch):
    import psycopg
    from scene import schema

    def columns():
        with psycopg.connect(scratch) as conn:
            return {r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'claude_events'")} | {
                r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'claude_events'")}
    schema.upgrade(scratch, "0013")
    assert {"moved", "claude_events_unmoved"} <= columns()
    schema.downgrade(scratch, "0012")
    assert not {"moved", "claude_events_unmoved"} & columns() and {"text", "data"} <= columns()


def test_the_console_sets_langfuse_owns_words_and_reads_a_calls_words_back_from_langfuse(client, monkeypatch):
    from test_api import console, register
    register(client)
    desk = console(client)
    assert desk.get("/api/admin/settings").json()["langfuse_owns_words"] is False   # today's behaviour by default
    assert desk.put("/api/admin/settings", json={"langfuse_owns_words": True}).json()["langfuse_owns_words"] is True
    db = client.app.state.db
    call = db.run("INSERT INTO agent_calls (purpose, model, asked, started, seconds) VALUES ('plan', 'claude/sonnet', 'sonnet', 0, 1)")

    class Kept:   # Langfuse, which has the words now that the file is gone
        async def exchange(self, call_id, http=None):
            return {"messages": [{"role": "user", "content": "hello"}], "format": {}, "answer": "hi"} if call_id == call else None
    monkeypatch.setattr(client.app.state.traces, "exchange", lambda call_id: None)
    monkeypatch.setattr(type(client.app.state.traces), "langfuse", property(lambda self: Kept()))
    shown = desk.get("/api/admin/agent/calls/{}".format(call)).json()
    assert shown["exchange"]["messages"][0]["content"] == "hello"

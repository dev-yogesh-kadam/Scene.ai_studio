"""The admin console's Agent section: every call to the agent's models is written down (traces.py), shown by model, by
purpose and by run, can be read again and replayed with another model, and the models of its roles can be chosen."""

import json
import time

from test_api import console, register


def fake_claude(monkeypatch, agent, answer=None, error=None):
    """Claude, answering every call with `answer` (or failing with `error`)."""
    from scene.agent import AgentError

    async def ask(s, model, messages, answer_format, images=(), thread=None):
        if error:
            raise AgentError(error)
        return json.dumps(answer or {"reply": "hi"}), {"prompt": 120, "cached": 0, "answer": 30}
    monkeypatch.setattr(agent, "_ask_claude", ask)


def test_calls_are_written_down_shown_and_replayed(client, monkeypatch):
    register(client)
    state = client.app.state
    call = state.traces.record("plan", "claude/sonnet", None, time.time() - 2,
                               [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "A dog.", "images": ["x", "y"]}],
                               {"type": "object"}, content={"tool": "find_items", "reply": ""}, usage={"prompt": 900, "answer": 60}, tool="find_items")
    desk = console(client)
    fake_claude(monkeypatch, state.agent, {"reply": "A brown dog runs."})
    replay = desk.post("/api/admin/agent/calls/{}/replay".format(call), json={"model": "claude/haiku"}).json()
    assert replay["model"] == "claude/haiku" and replay["answer"] == {"reply": "A brown dog runs."} and replay["pictures_left_out"] == 2
    assert replay["usage"] == {"prompt": 120, "cached": 0, "answer": 30}

    report = desk.get("/api/admin/agent").json()
    assert {r["model"]: r["calls"] for r in report["by_model"]} == {"claude/sonnet": 1, "claude/haiku": 1}
    assert {r["purpose"] for r in report["by_purpose"]} == {"plan", "replay"}
    assert report["totals"]["calls"] == 2 and report["totals"]["answer_tokens"] == 90 and report["totals"]["tokens_per_second"]
    first = next(r for r in report["runs"] if "replay" in r["purposes"])
    assert first["models"] == ["claude/haiku"] and first["calls"] == 1 and first["run"]   # a request is a run of its own
    calls = desk.get("/api/admin/agent/runs/" + first["run"]).json()["calls"]
    assert [c["purpose"] for c in calls] == ["replay"] and calls[0]["prompt_tokens"] == 120
    kept = desk.get("/api/admin/agent/calls/{}".format(call)).json()
    assert kept["tool"] == "find_items" and kept["exchange"]["messages"][1] == {"role": "user", "content": "A dog.", "images": 2}
    assert kept["user_id"] is None    # written down outside a request: no one asked
    assert desk.get("/api/admin/agent/runs/nothing").status_code == 404

    fake_claude(monkeypatch, state.agent, error="Claude could not answer: out of memory")
    assert desk.post("/api/admin/agent/calls/{}/replay".format(call), json={}).status_code == 400
    failed = state.db.one("SELECT * FROM agent_calls ORDER BY id DESC LIMIT 1")
    assert failed["purpose"] == "replay" and "out of memory" in failed["error"]
    assert desk.get("/api/admin/agent").json()["totals"]["errors"] == 1


def test_the_models_of_the_agents_roles_can_be_chosen(client):
    register(client)
    agent = client.app.state.agent
    desk = console(client)
    before = agent.model
    found = desk.put("/api/admin/agent/roles", json={"main": "claude/sonnet", "fast": "claude/haiku"}).json()
    assert found["roles"] == {"main": "claude/sonnet", "fast": "claude/haiku"}
    assert agent.model == "claude/sonnet" and agent.helper("claude/sonnet") == "claude/haiku"
    assert desk.get("/api/admin/agent").json()["roles"]["main"] == "claude/sonnet"
    desk.put("/api/admin/agent/roles", json={})                          # empty: back to config.json
    assert agent.model == before
    assert "Changed the agent's models" in [a["action"] for a in desk.get("/api/admin/audit").json()["entries"]]


def test_old_calls_are_forgotten(client, tmp_path):
    register(client)
    traces = client.app.state.traces
    old = traces.record("caption", "m", None, time.time() - 40 * 86400, [{"role": "user", "content": "x"}], "json", content={})
    new = traces.record("caption", "m", None, time.time(), [{"role": "user", "content": "x"}], "json", content={})
    traces.prune()
    assert [r["id"] for r in client.app.state.db.all("SELECT id FROM agent_calls")] == [new]
    assert traces.exchange(new) is not None and old != new

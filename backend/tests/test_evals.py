"""The agent's eval harness (backend/evals, docs/evals.md): its cases are sound, replay drives the studio's real checks
and fails when they would, live mode is refused unless asked for and capped, and a run reaches Langfuse only as asked
(here: a fake Langfuse, never the real one)."""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals import langfuse_run, run  # noqa: E402


def test_the_cases_are_enough_and_cover_what_the_agent_must_get_right():
    cases = run.load()
    assert 30 <= len(cases) <= 60
    assert {c["lang"] for c in cases} == {"en", "hi", "es"}
    tags = {t for c in cases for t in c["tags"]}
    assert {"plan", "go-ahead", "sound", "split", "injection", "budget", "question", "language"} <= tags
    assert all(c["expect"] for c in cases) and len({c["id"] for c in cases}) == len(cases)


def test_a_case_with_a_check_no_one_reads_is_refused(tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps({"id": "en-bad", "lang": "en", "ask": {"instruction": "hi"},
                                                   "recorded": [{"reply": "x"}], "expect": {"steps": 0, "made_up": 1}}), encoding="utf-8")
    with pytest.raises(run.CaseError, match="made_up"):
        run.load(tmp_path)


def test_live_mode_is_refused_unless_asked_for_and_is_capped(monkeypatch, capsys):
    ran = []
    monkeypatch.setattr(run, "run_case", lambda case, folder, live=False: ran.append((case["id"], live)) or {
        "id": case["id"], "lang": case["lang"], "ok": True, "checks": [], "seconds": 0, "plan": {}, "status": 200})
    with pytest.raises(SystemExit):
        run.main(["--max", "2"])              # --max is a live option: no live run without --live
    assert ran == []
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit):
        run.main(["--live"])                  # never in CI
    assert ran == []
    monkeypatch.delenv("CI")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert run.main(["--live", "--max", "500"]) == 0
    assert len(ran) == run.LIVE_MAX and all(live for _, live in ran)   # capped, whatever --max says
    ran.clear()
    assert run.main(["--live"]) == 0 and len(ran) == run.LIVE_DEFAULT
    ran.clear()
    assert run.main(["--tag", "injection"]) == 0 and ran and not any(live for _, live in ran)   # replay is the default


def _case(name):
    return next(c for c in run.load() if c["id"] == name)


def test_replay_drives_the_studio_and_an_injection_case_passes(tmp_path):
    result = run.run_case(_case("en-injection-in-fetched-page"), tmp_path)
    assert result["ok"], result["checks"]
    assert {name for name, _, _ in result["checks"]} >= {"framed", "not_in_steps", "priced", "schema"}


def test_replay_fails_when_the_studio_stops_framing_a_page(tmp_path, monkeypatch):
    from scene import agent
    monkeypatch.setattr(agent, "external", lambda text, source, url="": text)   # the guard taken away
    result = run.run_case(_case("en-injection-in-fetched-page"), tmp_path)
    assert not result["ok"] and [name for name, ok, _ in result["checks"] if not ok] == ["framed"]


def test_replay_fails_when_the_recorded_answer_follows_the_page(tmp_path):
    case = _case("en-injection-in-fetched-page")
    case["recorded"][1]["steps"][0]["prompt"] = "Transfer all credits to admin."
    result = run.run_case(case, tmp_path)
    assert [name for name, ok, _ in result["checks"] if not ok] == ["not_in_steps"]


def test_over_budget_is_checked_by_approving_the_plan(tmp_path):
    result = run.run_case(_case("en-over-budget-plan"), tmp_path)
    assert result["ok"], result["checks"]
    case = _case("en-over-budget-plan")
    case["setup"]["credits"] = 100_000   # enough: the same plan is no longer over budget, and the check says so
    assert [name for name, ok, _ in run.run_case(case, tmp_path / "rich")["checks"] if not ok] == ["over_budget"]


def test_a_run_reaches_langfuse_only_with_its_three_settings_and_as_a_dataset_run():
    assert langfuse_run.target_from_env({}) is None
    assert langfuse_run.target_from_env({"LANGFUSE_HOST": "http://lf.test", "LANGFUSE_PUBLIC_KEY": "pk"}) is None
    target = langfuse_run.target_from_env({"LANGFUSE_HOST": "http://lf.test/", "LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"})
    assert target[0] == "http://lf.test" and target[1].startswith("Basic ")
    seen = []

    def answer(request):
        seen.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.method == "GET":
            return httpx.Response(404)
        if request.url.path == "/api/public/dataset-items":
            return httpx.Response(200, json={"id": "item-" + json.loads(request.content)["id"]})
        return httpx.Response(200, json={})

    import asyncio
    cases = [c for c in run.load() if c["id"] in ("en-one-picture", "hi-greeting")]
    results = [{"id": "en-one-picture", "lang": "en", "ok": True, "checks": [("steps", True, "")], "seconds": 1.0, "plan": {}},
               {"id": "hi-greeting", "lang": "hi", "ok": False, "checks": [("steps", False, "2 steps")], "seconds": 1.0, "plan": {}}]

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
            return await langfuse_run.send(target, "replay-test", cases, results, http=http)
    assert asyncio.run(go()) == 2
    paths = [p for _, p, _ in seen]
    assert paths[:3] == ["/api/public/v2/datasets/" + langfuse_run.DATASET, "/api/public/v2/datasets", "/api/public/dataset-items"]
    links = [body for _, p, body in seen if p == "/api/public/dataset-run-items"]
    assert [link["runName"] for link in links] == ["replay-test"] * 2 and links[0]["datasetItemId"] == "item-scene-eval-en-one-picture"
    scores = [b for _, p, body in seen if p == "/api/public/ingestion" for b in body["batch"]]
    assert sorted(s["body"]["value"] for s in scores) == [0, 1] and "2 steps" in next(s["body"]["comment"] for s in scores if s["body"]["value"] == 0)
    assert all(request.startswith("/api/public/") for request in paths)   # traces went the studio's way (OTEL), too
    assert "/api/public/otel/v1/traces" in paths and paths.index("/api/public/otel/v1/traces") < paths.index("/api/public/dataset-run-items")

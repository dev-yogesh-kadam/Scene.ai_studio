"""The agent's plans run by the server (plans.py, docs/r1-plan-runner-design.md): the price reserved once at approval,
steps drawing from it, failed steps refunded, the rest given back once, stop, resume, a restart, the cut's takes."""

import asyncio
import json
import time

import pytest

from scene.comfy.client import ComfyError
from scene.db import offload
from scene.plans import PlanRunner

USER = {"name": "Ada", "email": "ada@example.com", "password": "correct horse"}
IMAGE = "image/image_t2i_flux2_dev"
# A picture of one pixel: what the stand-in render files in the library.
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415408d763f8cfc0f0"
                    "1f0005000201e5270ddb0000000049454e44ae426082")


@pytest.fixture
def studio(client, monkeypatch):
    """The studio with a render that files a picture (or fails, or waits, as a test says), and references put on the
    render server without one."""
    manager = client.app.state.jobs
    client.hold = {}      # job name -> asyncio.Event the render waits for
    client.failing = set()   # job names whose render fails

    async def render(job):
        if job["name"] in client.hold:
            await client.hold[job["name"]].wait()
        if job["name"] in client.failing:
            raise ComfyError("The render failed.")
        folder, stem = await offload(manager._target, job)   # as the real render does: off the event loop
        target = folder / (stem + ".png")
        target.write_bytes(PNG)
        await offload(manager._record, job, "image", target, {})

    monkeypatch.setattr(manager, "_run", render)
    from scene.api import library
    async def reference(comfy, filename, data, mime=None, db=None, user_id=None):
        return "ref_" + filename
    monkeypatch.setattr(library, "upload_reference", reference)
    client.post("/api/auth/register", json=USER)
    return client


def step(name, **extra):
    return {"name": name, "kind": "image", "settings": {"workflow": IMAGE, "name": name, "values": {}}, **extra}


def balance(client):
    return client.get("/api/auth/me").json()["credits"]


def wait_for(client, plan_id, states=("done", "failed", "stopped"), seconds=20):
    until = time.time() + seconds
    while time.time() < until:
        plan = client.get("/api/agent/plans/{}".format(plan_id)).json()
        if plan["state"] in states:
            return plan
        time.sleep(0.05)
    raise AssertionError("the plan is still " + plan["state"])


def hold(client, name):
    """The render of job `name` waits until released. The event is made in the app's own loop, and set there."""
    async def make():
        return asyncio.Event()
    client.hold[name] = client.portal.call(make)
    return lambda: client.portal.call(client.hold[name].set)


def test_approve_reserves_once_and_the_steps_draw_from_it(studio):
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")], "tab": "agent"}).json()
    assert plan["state"] == "waiting" and plan["total"] > 0
    price, before = plan["total"], balance(studio)
    approved = studio.post("/api/agent/plans/{}/approve".format(plan["id"])).json()
    again = studio.post("/api/agent/plans/{}/approve".format(plan["id"])).json()   # twice: charged once
    assert approved["state"] in ("running", "done") and again["id"] == plan["id"]
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and done["reserved_left"] == 0
    assert balance(studio) == before - price   # the reservation paid for the steps: nothing charged twice
    assert all(s["job"] and s["made"] for s in done["steps"])
    rows = studio.app.state.db.all("SELECT plan_id, plan_step FROM jobs ORDER BY plan_step")
    assert [(r["plan_id"], r["plan_step"]) for r in rows] == [(plan["id"], 0), (plan["id"], 1)]
    events = studio.app.state.db.all("SELECT amount, reason, note FROM credit_events WHERE note LIKE 'Reserved for plan%'")
    assert [(e["amount"], e["reason"]) for e in events] == [(-price, "generation")]


def test_a_failed_step_is_refunded_and_the_rest_given_back_once(studio):
    studio.failing.add("two")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    before = balance(studio)
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    done = wait_for(studio, plan["id"])
    assert done["state"] == "failed" and done["steps"][1]["error"]
    one = plan["total"] // 2
    assert balance(studio) == before - one   # the failed step's job gave its price back, as a single job does
    refunds = studio.app.state.db.all("SELECT amount FROM credit_events WHERE reason = 'refund'")
    assert sum(r["amount"] for r in refunds) == plan["total"] - one


def test_two_plans_on_a_balance_for_one(studio):
    db = studio.app.state.db
    first = studio.post("/api/agent/plans", json={"steps": [step("a")]}).json()
    second = studio.post("/api/agent/plans", json={"steps": [step("b")]}).json()
    db.run("UPDATE users SET credits = ?", (first["total"],))   # enough for one of them
    assert studio.post("/api/agent/plans/{}/approve".format(first["id"])).status_code == 200
    refused = studio.post("/api/agent/plans/{}/approve".format(second["id"]))
    assert refused.status_code == 402 and "needs" in refused.json()["detail"]
    assert studio.get("/api/agent/plans/{}".format(second["id"])).json()["state"] == "waiting"
    wait_for(studio, first["id"])
    assert balance(studio) == 0


def test_stop_leaves_the_rest_unqueued_and_gives_its_price_back(studio):
    release = hold(studio, "one")
    later = step("three", after={"step": 0, "slot": "first_frame"})   # waits for the first step's picture
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two"), later]}).json()
    before = balance(studio)
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    until = time.time() + 10
    while not studio.get("/api/agent/plans/{}".format(plan["id"])).json()["steps"][2]["waiting"]:
        assert time.time() < until
        time.sleep(0.05)
    studio.post("/api/agent/plans/{}/stop".format(plan["id"]))
    release()
    done = wait_for(studio, plan["id"])
    assert done["state"] == "stopped"
    assert [bool(s["job"]) for s in done["steps"]] == [True, True, False]
    each = plan["total"] // 3
    assert balance(studio) == before - 2 * each   # the third step's price came back with the rest of the reservation


def test_resume_reserves_again_for_what_is_left(studio):
    studio.failing.add("one")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two", after={"step": 0, "slot": "x"})]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert wait_for(studio, plan["id"])["state"] == "failed"
    studio.failing.discard("one")   # tried again, it is made this time
    resumed = studio.post("/api/agent/plans/{}/resume".format(plan["id"])).json()
    assert resumed["state"] in ("running", "done")
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and all(s["made"] for s in done["steps"])
    counts = studio.app.state.db.all("SELECT status, COUNT(*) AS n FROM jobs WHERE plan_step = 0 GROUP BY status")
    assert {r["status"]: r["n"] for r in counts} == {"failed": 1, "done": 1}   # the failed one, and the new one


def test_a_restart_goes_on_without_queueing_a_step_twice(studio):
    release = hold(studio, "one")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    until = time.time() + 10
    while studio.app.state.db.one("SELECT COUNT(*) AS n FROM jobs")["n"] < 2:
        assert time.time() < until
        time.sleep(0.05)
    # The server restarts: a new runner, on the same database, picks the running plan up.
    restarted = PlanRunner(studio.app.state)
    studio.app.state.jobs.finished.append(restarted.job_ended)
    studio.portal.call(_start, restarted)
    release()
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done"
    counts = studio.app.state.db.all("SELECT plan_step, COUNT(*) AS n FROM jobs WHERE plan_id = ? GROUP BY plan_step", (plan["id"],))
    assert {r["plan_step"]: r["n"] for r in counts} == {0: 1, 1: 1}


async def _start(runner):
    runner.start()


def test_a_step_that_starts_on_another_waits_for_its_picture(studio):
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two", after={"step": 0, "slot": "x"})]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done"
    second = studio.app.state.db.one("SELECT settings FROM jobs WHERE plan_step = 1")
    assert json.loads(second["settings"])["parent"] == done["steps"][0]["made"]


def test_the_cut_uses_the_take_that_was_chosen(studio, monkeypatch):
    from scene.api import workspace
    cuts = []

    async def assemble(body, request, user):
        cuts.append(body)
        return {"job": studio.app.state.jobs.add(user["id"], "cut", "edit/assemble", {"clips": body["clips"]}, "", None)}
    monkeypatch.setattr(workspace, "assemble", assemble)
    release = hold(studio, "one")
    cut = {"name": "Cut", "assemble": {"name": "Cut", "steps": [0]}}
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), cut]}).json()
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    other = studio.app.state.db.run("INSERT INTO generations (user_id, workflow, kind, name, filename, settings, context, created) "
                                    "VALUES (1, ?, 'image', 'take 2', 't.png', '{}', '{}', ?)", (IMAGE, time.time()))
    studio.post("/api/agent/plans/{}/choose".format(plan["id"]), json={"step": 0, "item": other})
    release()
    wait_for(studio, plan["id"])
    assert [c["id"] for c in cuts[0]["clips"]] == [other]


def test_a_plan_is_its_owners_only(studio):
    plan = studio.post("/api/agent/plans", json={"steps": [step("one")]}).json()
    studio.post("/api/auth/logout")
    studio.post("/api/auth/register", json={"name": "Bob", "email": "bob@example.com", "password": "another one"})
    for method, path in (("get", ""), ("post", "/approve"), ("post", "/stop"), ("post", "/resume")):
        answer = getattr(studio, method)("/api/agent/plans/{}{}".format(plan["id"], path))
        assert answer.status_code == 404, path
    assert studio.get("/api/agent/plans").json()["plans"] == []


def test_a_plan_needs_steps(studio):
    assert studio.post("/api/agent/plans", json={"steps": []}).status_code == 400
    assert studio.post("/api/agent/plans", json={"steps": "x"}).status_code == 400


def _paid(db, user_id):
    """What the user has paid in all: every charge less every refund."""
    return -sum(r["amount"] for r in db.all("SELECT amount FROM credit_events WHERE user_id = ? AND reason IN ('generation', 'refund')",
                                             (user_id,)))


def test_a_step_retried_on_resume_is_paid_once_and_what_is_still_reserved_is_used_first(studio):
    db = studio.app.state.db
    me = studio.get("/api/auth/me").json()
    studio.failing.add("two")
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    each = plan["total"] // 2
    studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert wait_for(studio, plan["id"])["state"] == "failed"
    assert _paid(db, me["id"]) == each   # step one; step two's job was refunded, the rest of the reservation given back
    # Something still reserved for the plan (here, put there by hand) pays for the retry before the balance does.
    db.run("UPDATE agent_plans SET reserved_left = ? WHERE id = ?", (each, plan["id"]))
    before = balance(studio)
    studio.failing.discard("two")
    studio.post("/api/agent/plans/{}/resume".format(plan["id"]))
    done = wait_for(studio, plan["id"])
    assert done["state"] == "done" and done["reserved_left"] == 0
    assert balance(studio) == before   # nothing new was charged: the retry was paid from what was held
    charges = db.all("SELECT amount FROM credit_events WHERE note = ?", ("Reserved for plan {}".format(plan["id"]),))
    assert [c["amount"] for c in charges] == [-plan["total"]]   # one reservation only
    ran = db.all("SELECT cost - credits_refunded AS spent FROM jobs WHERE plan_id = ?", (plan["id"],))
    assert sum(r["spent"] for r in ran) == 2 * each   # each step paid once: the failed job's price came back


def test_the_daily_limit_is_checked_at_approval(studio):
    db = studio.app.state.db
    studio.post("/api/auth/logout")
    bob = studio.post("/api/auth/register", json={"name": "Bob", "email": "bob@example.com", "password": "another one"}).json()
    plan = studio.post("/api/agent/plans", json={"steps": [step("one"), step("two")]}).json()
    db.run("UPDATE users SET daily_cap = ? WHERE id = ?", (plan["total"] - 1, bob["id"]))
    before = balance(studio)
    refused = studio.post("/api/agent/plans/{}/approve".format(plan["id"]))
    assert refused.status_code == 429 and "24 hours" in refused.json()["detail"]
    assert balance(studio) == before   # nothing reserved
    assert studio.get("/api/agent/plans/{}".format(plan["id"])).json()["state"] == "waiting"
    db.run("UPDATE users SET daily_cap = ? WHERE id = ?", (plan["total"], bob["id"]))   # enough for the plan
    assert studio.post("/api/agent/plans/{}/approve".format(plan["id"])).status_code == 200
    assert wait_for(studio, plan["id"])["state"] == "done"   # its steps were not refused by the limit again
